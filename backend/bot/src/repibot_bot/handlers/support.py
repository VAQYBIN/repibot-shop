"""Поддержка в боте: обращение из лички и ответ сотрудника из топика.

Обе стороны разговора сходятся в одном роутере, потому что фильтры у них
взаимоисключающие и разъехаться не должны: личка — это человек, супергруппа с
настроенным номером — это персонал, а всё остальное сюда не относится.

Роутер собирается только там, где супергруппа задана: без неё обращение
некуда доставить, и команда `/support`, которая ничем не заканчивается,
хуже её отсутствия.
"""

from __future__ import annotations

from collections.abc import Coroutine
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Ticket, TicketStatus, User
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.i18n import translate
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.services.errors import ServiceError
from repibot_core.services.moderation import ModerationService
from repibot_core.services.support import SupportService
from repibot_core.services.support_card import build_card, devices_for_card
from repibot_core.settings import Settings, get_settings
from repibot_core.tasks import wake_outbox

# Ответы персоналу — русские строки рядом с обработчиком: супергруппа это
# рабочее место, а не интерфейс клиента, и второго языка в ней не заводим.
CONFIRM_CLOSED = "Обращение №{id} закрыто, человек уведомлён."
CONFIRM_CLOSED_SILENT = "Обращение №{id} закрыто без уведомления."
CONFIRM_MUTED = "Поддержка для этого человека закрыта."
CONFIRM_UNMUTED = "Поддержка снова открыта."
CONFIRM_BANNED = "Аккаунт заблокирован, обращение №{id} закрыто."
CONFIRM_UNBANNED = "Блокировка снята."

# Отказы отвечают так же, как подтверждения: молчание в ответ на команду
# сотрудник читает как «бот сломался», а не как «ничего не изменилось».
ALREADY_CLOSED = "Обращение уже закрыто."
ALREADY_MUTED = "Поддержка для этого человека уже закрыта."
ALREADY_OPEN = "Поддержка и так открыта."
ALREADY_BANNED = "Аккаунт уже заблокирован."
NOT_BANNED = "Аккаунт не заблокирован."
STAFF_IMMUNE = "Это сотрудник — заблокировать нельзя."
ACCOUNT_GONE = "Аккаунт удалён — команду применять не к кому."


async def handle_support_command(
    message: Message,
    command: CommandObject,
    user: User,
    language: str,
    session: AsyncSession,
) -> None:
    """`/support` в личке: открывает обращение или показывает уже открытое.

    Текст берётся прямо из команды, а не спрашивается вторым сообщением: шаг
    с ожиданием ответа — это состояние, которое переживает перезапуск бота и
    ловит чужие реплики, а выигрыш от него ровно один пробел.
    """
    service = SupportService(session)
    text = (command.args or "").strip()
    existing = await _open_ticket(service, user.id)
    if not text:
        if existing is None:
            await message.answer(translate(language, "bot.support.ask"))
        else:
            await message.answer(translate(language, "bot.support.opened", id=existing.id))
        return

    try:
        ticket = await service.open(user.id, text)
    except ServiceError as refusal:
        if refusal.code == "support_muted":
            # Заглушённому закрыт разговор, и он обязан узнать об этом словами:
            # молчащий бот выглядит сломанным, а не запрещающим.
            await message.answer(translate(language, "bot.support.muted"))
            return
        # Предел открытых обращений исчерпан. Молчать нельзя: вопрос уже
        # написан — он уходит в тот разговор, который у человека идёт.
        if existing is None:
            raise
        await service.reply_from_user(user.id, existing.id, text)
        await session.commit()
        await wake_outbox()
        await message.answer(translate(language, "bot.support.opened", id=existing.id))
        return

    await session.commit()
    # Разбор очереди идёт раз в минуту, и ждать её человеку незачем: тема
    # супергруппы иначе появилась бы только к следующему прогону крона.
    await wake_outbox()
    await message.answer(translate(language, "bot.support.opened", id=ticket.id))


async def handle_private_message(
    message: Message, user: User, language: str, session: AsyncSession
) -> None:
    """Обычное сообщение в личке — продолжение открытого обращения.

    Без открытого обращения это подсказка, а не новое обращение: иначе
    случайное «привет» заводит топик в супергруппе, на который персоналу
    нечего отвечать.
    """
    text = (message.text or "").strip()
    if not text:
        return
    service = SupportService(session)
    ticket = await _open_ticket(service, user.id)
    if ticket is None:
        await message.answer(translate(language, "bot.support.no_open"))
        return

    try:
        await service.reply_from_user(user.id, ticket.id, text)
    except ServiceError as refusal:
        if refusal.code != "support_muted":
            raise
        await message.answer(translate(language, "bot.support.muted"))
        return

    await session.commit()
    await wake_outbox()
    await message.answer(translate(language, "bot.support.opened", id=ticket.id))


async def handle_topic_message(message: Message, session: AsyncSession) -> None:
    """Сообщение из топика супергруппы — ответ поддержки этому обращению."""
    sender = message.from_user
    # Сообщение от самого бота обязано быть отброшено: реплика пользователя,
    # пересланная в топик, вернулась бы ему же как «ответ поддержки», и
    # переписка зациклилась бы.
    if sender is None or sender.is_bot:
        return
    topic_id = message.message_thread_id
    if topic_id is None:
        return
    # Подпись под вложением — тоже ответ: сотрудник присылает скриншот и
    # объяснение к нему одним сообщением.
    text = (message.text or message.caption or "").strip()
    if not text:
        return

    await SupportService(session).reply_from_staff(
        topic_id, text, telegram_id=sender.id, message_id=message.message_id
    )
    await session.commit()
    # Ответ уже лежит в теме, но название темы после него меняет цвет: просьба
    # переименовать ушла в очередь, и ждать её разбора кроном незачем.
    await wake_outbox()


async def handle_topic_info(
    message: Message, session: AsyncSession, panel_devices: PanelDevices
) -> None:
    """`/info` присылает карточку собеседника заново, со свежими данными.

    Отдельным сообщением, а не правкой первого: правка выше по ленте проходит
    незамеченной, а спрашивают именно тогда, когда данные могли измениться.
    """
    ticket = await _ticket_of_topic(session, message)
    if ticket is None:
        return

    devices = await devices_for_card(session, panel_devices, ticket.user_id)
    await message.answer(await build_card(session, ticket, devices=devices))


async def handle_topic_close(message: Message, user: User, session: AsyncSession) -> None:
    """`/close` закрывает обращение вместе с темой и говорит об этом человеку."""
    await _close(message, user, session, notify=True, confirm=CONFIRM_CLOSED)


async def handle_topic_close_silent(message: Message, user: User, session: AsyncSession) -> None:
    """`/close_silent` — то же самое молча: разговор кончился ничем."""
    await _close(message, user, session, notify=False, confirm=CONFIRM_CLOSED_SILENT)


async def handle_topic_mute(message: Message, user: User, session: AsyncSession) -> None:
    """`/mute` закрывает собеседнику разговор, не трогая подписку и оплату."""
    ticket = await _ticket_of_topic(session, message)
    if ticket is None:
        return

    await _moderate(
        message,
        session,
        ModerationService(session).mute_support(ticket.user_id, actor_id=user.id),
        done=CONFIRM_MUTED,
        already=ALREADY_MUTED,
    )


async def handle_topic_unmute(message: Message, user: User, session: AsyncSession) -> None:
    """`/unmute` снова открывает разговор."""
    ticket = await _ticket_of_topic(session, message)
    if ticket is None:
        return

    await _moderate(
        message,
        session,
        ModerationService(session).unmute_support(ticket.user_id, actor_id=user.id),
        done=CONFIRM_UNMUTED,
        already=ALREADY_OPEN,
    )


async def handle_topic_ban(message: Message, user: User, session: AsyncSession) -> None:
    """`/ban` закрывает аккаунт целиком и тихо закрывает обращение.

    Тихо — потому что уведомление о закрытии ушло бы человеку, которого этой
    же командой лишили и бота, и кабинета: отвечать заблокированному некому.
    """
    ticket = await _ticket_of_topic(session, message)
    if ticket is None:
        return

    try:
        changed = await ModerationService(session).ban(ticket.user_id, actor_id=user.id)
    except ServiceError as refusal:
        await message.answer(_refusal(refusal))
        return
    if not changed:
        await message.answer(ALREADY_BANNED)
        return

    await SupportService(session).close(ticket.id, by_staff=True, notify=False)
    await _record_close(session, ticket.id, actor_id=user.id)
    await session.commit()
    await wake_outbox()
    await message.answer(CONFIRM_BANNED.format(id=ticket.id))


async def handle_topic_unban(message: Message, user: User, session: AsyncSession) -> None:
    """`/unban` снимает блокировку."""
    ticket = await _ticket_of_topic(session, message)
    if ticket is None:
        return

    await _moderate(
        message,
        session,
        ModerationService(session).unban(ticket.user_id, actor_id=user.id),
        done=CONFIRM_UNBANNED,
        already=NOT_BANNED,
    )


async def _close(
    message: Message, user: User, session: AsyncSession, *, notify: bool, confirm: str
) -> None:
    """Общая часть обоих закрытий: они различаются только уведомлением."""
    ticket = await _ticket_of_topic(session, message)
    if ticket is None:
        return
    if ticket.status is TicketStatus.closed:
        # Сервис пропускает повтор молча, но сотруднику нужно знать, что
        # команда ничего не изменила: иначе он ждёт, когда закроется тема.
        await message.answer(ALREADY_CLOSED)
        return

    await SupportService(session).close(ticket.id, by_staff=True, notify=notify)
    await _record_close(session, ticket.id, actor_id=user.id)
    await session.commit()
    await wake_outbox()
    await message.answer(confirm.format(id=ticket.id))


async def _moderate(
    message: Message,
    session: AsyncSession,
    change: Coroutine[Any, Any, bool],
    *,
    done: str,
    already: str,
) -> None:
    """Применить решение, зафиксировать его и ответить в тему.

    Ответ обязателен в любом исходе: без него сотрудник не отличит
    сработавшую команду от опечатки, а повтор — от настоящего изменения.
    """
    try:
        changed = await change
    except ServiceError as refusal:
        await message.answer(_refusal(refusal))
        return
    if not changed:
        await message.answer(already)
        return

    await session.commit()
    await message.answer(done)


async def _record_close(session: AsyncSession, ticket_id: int, *, actor_id: int) -> None:
    """Кто закрыл обращение.

    Журнал ведёт вызывающий, а не сервис: закрытие из кабинета делает сам
    человек, и записывать его как действие персонала было бы неправдой. Тем
    же приёмом пишет закрытие админка.
    """
    await AuditRepository(session).record(
        "ticket.close",
        "ticket",
        actor_id=actor_id,
        entity_id=str(ticket_id),
        after={"status": TicketStatus.closed.value},
    )


def _refusal(error: ServiceError) -> str:
    """Оба отказа модерации словами: сотруднику важно, почему не вышло."""
    return STAFF_IMMUNE if error.code == "staff_immune" else ACCOUNT_GONE


async def _ticket_of_topic(session: AsyncSession, message: Message) -> Ticket | None:
    """Обращение этой темы.

    Сервис ищет обращение по теме только внутри ответа сотрудника, а командам
    нужен сам номер. Выборка здесь, а не второй метод в сервисе: у неё нет
    никакой логики. Посторонняя тема молча игнорируется — в супергруппе
    поддержки бывают темы, к обращениям отношения не имеющие.
    """
    sender = message.from_user
    if sender is None or sender.is_bot:
        return None
    topic_id = message.message_thread_id
    if topic_id is None:
        return None
    # Тип назван явно: `scalar` объявлен возвращающим Any, и без этого
    # вызывающие получили бы Any вместо обращения.
    found: Ticket | None = await session.scalar(
        select(Ticket).where(Ticket.telegram_topic_id == topic_id)
    )
    return found


async def _open_ticket(service: SupportService, user_id: int) -> Ticket | None:
    """Самое свежее незакрытое обращение — то, в котором идёт разговор."""
    for ticket in await service.list_for_user(user_id):
        if ticket.status is not TicketStatus.closed:
            return ticket
    return None


def build_support_router(settings: Settings | None = None) -> Router:
    """Новый роутер на каждый вызов: aiogram не даёт делить его двумя диспетчерами."""
    resolved = settings or get_settings()
    # Фильтр по номеру чата, а не по типу «супергруппа»: в любой другой
    # супергруппе, куда добавили бота, переписки поддержки нет.
    in_support_chat = F.chat.id == resolved.support_chat_id
    private = F.chat.type == "private"

    router = Router(name="support")
    # Все семь команд идут до обработчика обычных сообщений: иначе их текст
    # уходит человеку как ответ поддержки, и вместо запрета он получает «/mute».
    router.message.register(handle_topic_info, in_support_chat, Command("info"))
    router.message.register(handle_topic_close, in_support_chat, Command("close"))
    router.message.register(handle_topic_close_silent, in_support_chat, Command("close_silent"))
    router.message.register(handle_topic_mute, in_support_chat, Command("mute"))
    router.message.register(handle_topic_unmute, in_support_chat, Command("unmute"))
    router.message.register(handle_topic_ban, in_support_chat, Command("ban"))
    router.message.register(handle_topic_unban, in_support_chat, Command("unban"))
    router.message.register(handle_topic_message, in_support_chat, F.message_thread_id)
    router.message.register(handle_support_command, private, Command("support"))
    # Прочие команды исключены явно: этот роутер подключается последним, и без
    # исключения он превратил бы опечатку в команде в реплику поддержке.
    router.message.register(handle_private_message, private, F.text, ~F.text.startswith("/"))
    return router
