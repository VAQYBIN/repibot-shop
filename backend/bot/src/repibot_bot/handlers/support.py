"""Поддержка в боте: обращение из лички и ответ сотрудника из топика.

Обе стороны разговора сходятся в одном роутере, потому что фильтры у них
взаимоисключающие и разъехаться не должны: личка — это человек, супергруппа с
настроенным номером — это персонал, а всё остальное сюда не относится.

Роутер собирается только там, где супергруппа задана: без неё обращение
некуда доставить, и команда `/support`, которая ничем не заканчивается,
хуже её отсутствия.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Ticket, TicketStatus, User
from repibot_core.i18n import translate
from repibot_core.services.errors import ServiceError
from repibot_core.services.support import SupportService
from repibot_core.settings import Settings, get_settings


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
    except ServiceError:
        # Предел открытых обращений исчерпан. Молчать нельзя: вопрос уже
        # написан — он уходит в тот разговор, который у человека идёт.
        if existing is None:
            raise
        await service.reply_from_user(user.id, existing.id, text)
        await session.commit()
        await message.answer(translate(language, "bot.support.opened", id=existing.id))
        return

    await session.commit()
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

    await service.reply_from_user(user.id, ticket.id, text)
    await session.commit()
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


async def handle_topic_close(message: Message, language: str, session: AsyncSession) -> None:
    """`/close` в топике закрывает обращение вместе с самим топиком."""
    sender = message.from_user
    if sender is None or sender.is_bot:
        return
    topic_id = message.message_thread_id
    if topic_id is None:
        return
    # Сервис ищет обращение по топику только внутри ответа сотрудника, а
    # закрытию нужен номер. Выборка здесь, а не второй метод в сервисе:
    # у неё один вызов и никакой логики.
    ticket = await session.scalar(select(Ticket).where(Ticket.telegram_topic_id == topic_id))
    if ticket is None:
        return

    await SupportService(session).close(ticket.id, by_staff=True)
    await session.commit()
    await message.answer(translate(language, "bot.support.closed", id=ticket.id))


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
    # `/close` идёт первым: иначе его текст ушёл бы в переписку как ответ.
    router.message.register(handle_topic_close, in_support_chat, Command("close"))
    router.message.register(handle_topic_message, in_support_chat, F.message_thread_id)
    router.message.register(handle_support_command, private, Command("support"))
    # Прочие команды исключены явно: этот роутер подключается последним, и без
    # исключения он превратил бы опечатку в команде в реплику поддержке.
    router.message.register(handle_private_message, private, F.text, ~F.text.startswith("/"))
    return router
