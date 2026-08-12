"""Поддержка в боте: обе стороны разговора.

Проверяется не база, а маршрутизация: какое сообщение доходит до сервиса
переписки, а какое обязано быть отброшено. Сервис подменяется двойником —
у него уже есть свой набор в `backend/core/tests/test_tickets.py`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_bot.handlers import support as support_handlers
from repibot_bot.handlers.support import (
    build_support_router,
    handle_private_message,
    handle_support_command,
)
from repibot_bot.main import build_dispatcher
from repibot_core.db.models import (
    AuditLog,
    NotificationDelivery,
    Ticket,
    TicketAuthor,
    TicketMessage,
    TicketStatus,
    User,
    UserRole,
    UserStatus,
)
from repibot_core.services.errors import ServiceError
from repibot_core.services.support import SupportService
from repibot_core.settings import get_settings

SUPPORT_CHAT_ID = -1_002_000_000_001
FOREIGN_CHAT_ID = -1_002_999_999_999
TOPIC_ID = 12


@pytest.fixture(autouse=True)
def wake_ups(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Пробуждение очереди без брокера.

    Проверяется, что его вообще позвали, а не что Valkey отвечает: настоящий
    вызов ходил бы в сеть за несуществующим брокером и стоил бы секунд
    ожидания на каждой команде.
    """
    from repibot_core.tasks import process_outbox

    woken: list[str] = []

    async def _wake() -> None:
        woken.append("outbox")

    monkeypatch.setattr(process_outbox, "kiq", _wake)
    return woken


@dataclass
class FakeTicket:
    """Ровно то, что хендлер читает у обращения: номер и чей ход."""

    id: int
    status: TicketStatus = TicketStatus.waiting_staff


@dataclass
class RecordingSupport:
    """Двойник `SupportService`: тесту важно, дошёл ли вызов и с чем."""

    tickets: list[FakeTicket] = field(default_factory=list)
    opened: list[tuple[int, str]] = field(default_factory=list)
    user_replies: list[tuple[int, int, str]] = field(default_factory=list)
    staff_replies: list[tuple[int, str, int, int]] = field(default_factory=list)
    closed: list[tuple[int, bool, bool]] = field(default_factory=list)

    async def open(self, user_id: int, body: str) -> FakeTicket:
        self.opened.append((user_id, body))
        ticket = FakeTicket(id=100 + len(self.opened))
        self.tickets.insert(0, ticket)
        return ticket

    async def reply_from_user(self, user_id: int, ticket_id: int, body: str) -> None:
        self.user_replies.append((user_id, ticket_id, body))

    async def reply_from_staff(
        self, topic_id: int, body: str, *, telegram_id: int, message_id: int
    ) -> None:
        self.staff_replies.append((topic_id, body, telegram_id, message_id))

    async def close(self, ticket_id: int, *, by_staff: bool, notify: bool) -> None:
        self.closed.append((ticket_id, by_staff, notify))

    async def list_for_user(self, user_id: int) -> list[FakeTicket]:
        return list(self.tickets)


class RecordingSession(BaseSession):
    """Bot без сети: диспетчер обязан работать, ничего никуда не отправляя.

    Отправленное запоминается: ответ команды в теме — единственное, чем
    сотрудник отличает сработавшую команду от опечатки, и проверять его надо.
    """

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[Any] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self,
        bot: Bot,
        method: Any,
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
        self.sent.append(method)
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109
        chunk_size: int = 65_536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes]:
        del url, headers, timeout, chunk_size, raise_for_status
        if False:
            yield b""


def _use_double(monkeypatch: pytest.MonkeyPatch, double: RecordingSupport) -> None:
    monkeypatch.setattr(support_handlers, "SupportService", lambda session, settings=None: double)


def _topic_update(
    *,
    is_bot: bool,
    chat_id: int = SUPPORT_CHAT_ID,
    text: str = "Ответ",
    topic_id: int = TOPIC_ID,
) -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 42,
                "date": 0,
                "message_thread_id": topic_id,
                "chat": {"id": chat_id, "type": "supergroup", "is_forum": True},
                "from": {"id": 555, "is_bot": is_bot, "first_name": "Staff"},
                "text": text,
            },
        }
    )


def _support_dispatcher() -> Dispatcher:
    settings = get_settings().model_copy(update={"support_chat_id": SUPPORT_CHAT_ID})
    dispatcher = Dispatcher()
    dispatcher.include_router(build_support_router(settings))
    return dispatcher


def _user() -> User:
    return User(id=7, telegram_id=700_777, referral_code="SUPP0001", language="ru")


async def test_bot_own_message_in_the_topic_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Наше же сообщение, пересланное в топик, не должно вернуться человеку.

    Без этой проверки каждая реплика пользователя приходила бы ему обратно
    как ответ поддержки — и переписка зациклилась бы.
    """
    double = RecordingSupport()
    _use_double(monkeypatch, double)
    bot = Bot(token="123456:test-token", session=RecordingSession())

    await _support_dispatcher().feed_update(
        bot, _topic_update(is_bot=True), session=AsyncMock(), language="ru", user=_user()
    )

    assert double.staff_replies == []


async def test_staff_message_in_the_topic_reaches_the_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сообщение живого сотрудника — это ответ по обращению этого топика."""
    double = RecordingSupport()
    _use_double(monkeypatch, double)
    bot = Bot(token="123456:test-token", session=RecordingSession())

    await _support_dispatcher().feed_update(
        bot,
        _topic_update(is_bot=False, text="Проверьте профиль"),
        session=AsyncMock(),
        language="ru",
        user=_user(),
    )

    assert double.staff_replies == [(TOPIC_ID, "Проверьте профиль", 555, 42)]


async def test_foreign_supergroup_is_not_our_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Чужая супергруппа с темами не должна попадать в нашу переписку."""
    double = RecordingSupport()
    _use_double(monkeypatch, double)
    bot = Bot(token="123456:test-token", session=RecordingSession())

    await _support_dispatcher().feed_update(
        bot,
        _topic_update(is_bot=False, chat_id=FOREIGN_CHAT_ID),
        session=AsyncMock(),
        language="ru",
        user=_user(),
    )

    assert double.staff_replies == []


async def test_plain_message_without_a_ticket_only_hints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Случайное «привет» в личке не должно становиться обращением."""
    double = RecordingSupport()
    _use_double(monkeypatch, double)
    message = MagicMock()
    message.text = "привет"
    message.answer = AsyncMock()

    await handle_private_message(message, user=_user(), language="ru", session=AsyncMock())

    assert double.opened == []
    assert double.user_replies == []
    assert "/support" in message.answer.await_args.args[0]


async def test_plain_message_continues_the_open_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    """При открытом обращении диалог с ботом и есть переписка с поддержкой."""
    double = RecordingSupport(tickets=[FakeTicket(id=17)])
    _use_double(monkeypatch, double)
    message = MagicMock()
    message.text = "  всё ещё не работает  "
    message.answer = AsyncMock()

    await handle_private_message(message, user=_user(), language="ru", session=AsyncMock())

    assert double.user_replies == [(7, 17, "всё ещё не работает")]


class MutedSupport(RecordingSupport):
    """Сервис, который заглушённому отказывает: так его видит бот."""

    async def open(self, user_id: int, body: str) -> FakeTicket:
        msg = "доступ к поддержке ограничен"
        raise ServiceError(msg, "support_muted")

    async def reply_from_user(self, user_id: int, ticket_id: int, body: str) -> None:
        msg = "доступ к поддержке ограничен"
        raise ServiceError(msg, "support_muted")


async def test_a_muted_person_hears_the_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отказ обязан дойти словами: молчащий бот выглядит сломанным, а не запрещающим.

    Проверяются оба входа в разговор — команда и обычное сообщение: заглушение
    закрывает разговор целиком, а не одну его половину.
    """
    double = MutedSupport(tickets=[FakeTicket(id=21)])
    _use_double(monkeypatch, double)
    plain = MagicMock()
    plain.text = "впустите"
    plain.answer = AsyncMock()
    asked = MagicMock()
    asked.answer = AsyncMock()
    command = MagicMock()
    command.args = "впустите"

    await handle_private_message(plain, user=_user(), language="ru", session=AsyncMock())
    await handle_support_command(
        asked, command=command, user=_user(), language="ru", session=AsyncMock()
    )

    assert "ограничен" in plain.answer.await_args.args[0]
    assert "ограничен" in asked.answer.await_args.args[0]


async def test_support_command_with_text_opens_a_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    """Текст сразу после команды — это уже обращение, второго шага не нужно."""
    double = RecordingSupport()
    _use_double(monkeypatch, double)
    message = MagicMock()
    message.answer = AsyncMock()
    command = MagicMock()
    command.args = "не открывается оплата"

    await handle_support_command(
        message, command=command, user=_user(), language="ru", session=AsyncMock()
    )

    assert double.opened == [(7, "не открывается оплата")]


async def _ticket_in_topic(session: AsyncSession) -> Ticket:
    """Обращение с уже созданным топиком — то состояние, в котором его закрывают."""
    user = User(telegram_id=700_778, referral_code="SUPPCLOS", language="ru")
    session.add(user)
    await session.flush()
    settings = get_settings().model_copy(update={"support_chat_id": SUPPORT_CHAT_ID})
    ticket = await SupportService(session, settings).open(user.id, "не открывается")
    ticket.telegram_topic_id = TOPIC_ID
    await session.commit()
    return ticket


async def test_close_in_the_topic_closes_the_ticket(db_session: AsyncSession) -> None:
    """`/close` в топике — единственный хендлер со своей выборкой из базы.

    Он ищет обращение по номеру темы, поэтому проверяется на настоящей базе,
    а не на двойнике: подмена сервиса как раз спрятала бы эту выборку.
    """
    ticket = await _ticket_in_topic(db_session)
    staff = await _staff(db_session)
    bot = Bot(token="123456:test-token", session=RecordingSession())

    await _support_dispatcher().feed_update(
        bot, _topic_update(is_bot=False, text="/close"), session=db_session, user=staff
    )

    await db_session.refresh(ticket)
    thread = await SupportService(db_session).thread(ticket.id)
    assert ticket.status is TicketStatus.closed
    assert [message.author_kind for message in thread] == [TicketAuthor.user, TicketAuthor.system]


async def test_close_in_an_unknown_topic_changes_nothing(db_session: AsyncSession) -> None:
    """Чужая тема без обращения не должна ни падать, ни закрывать соседнее."""
    ticket = await _ticket_in_topic(db_session)
    staff = await _staff(db_session)
    bot = Bot(token="123456:test-token", session=RecordingSession())

    await _support_dispatcher().feed_update(
        bot,
        _topic_update(is_bot=False, text="/close", topic_id=TOPIC_ID + 1),
        session=db_session,
        user=staff,
    )

    await db_session.refresh(ticket)
    messages = await db_session.scalar(select(func.count()).select_from(TicketMessage))
    assert ticket.status is TicketStatus.waiting_staff
    assert messages == 1


class EmptyPanel:
    """Панель без устройств: карточке хватает и такого ответа."""

    async def list(self, panel_id: int) -> list[object]:
        return []


async def _staff(session: AsyncSession) -> User:
    """Сотрудник, пишущий в тему: его номер уходит в журнал как автор решения."""
    staff = User(telegram_id=555, referral_code="SUPPSTAF", language="ru", role=UserRole.support)
    session.add(staff)
    await session.commit()
    return staff


async def _command(bot: Bot, text: str, session: AsyncSession, staff: User) -> None:
    """Команда в теме от живого сотрудника — так её видит хендлер из middleware."""
    await _support_dispatcher().feed_update(
        bot,
        _topic_update(is_bot=False, text=text),
        session=session,
        language="ru",
        user=staff,
        panel_devices=EmptyPanel(),
    )


def _answers(telegram: RecordingSession) -> list[str]:
    """Тексты, ушедшие в тему: подтверждения и отказы команд."""
    return [str(method.text) for method in telegram.sent if getattr(method, "text", None)]


async def _kinds(session: AsyncSession) -> list[str]:
    return list(await session.scalars(select(NotificationDelivery.kind)))


async def test_info_answers_with_a_card_and_writes_nothing_to_the_thread(
    db_session: AsyncSession,
) -> None:
    """`/info` — способ увидеть свежие данные, а не реплика человеку.

    Уйди она в переписку — собеседник получил бы «/info» ответом поддержки.
    """
    ticket = await _ticket_in_topic(db_session)
    staff = await _staff(db_session)
    telegram = RecordingSession()

    await _command(Bot(token="123456:test-token", session=telegram), "/info", db_session, staff)

    thread = await SupportService(db_session).thread(ticket.id)
    assert _answers(telegram)[-1].startswith("👤")
    assert "/close_silent" in _answers(telegram)[-1]
    assert [message.author_kind for message in thread] == [TicketAuthor.user]


async def test_close_confirms_in_the_topic_and_tells_the_person(
    db_session: AsyncSession, wake_ups: list[str]
) -> None:
    """Иначе человек узнаёт о закрытии, только заглянув в кабинет.

    Заодно проверяется пробуждение очереди: без него закрытая тема ждала бы
    крона до минуты, и сотрудник видел бы её открытой.
    """
    ticket = await _ticket_in_topic(db_session)
    staff = await _staff(db_session)
    telegram = RecordingSession()

    await _command(Bot(token="123456:test-token", session=telegram), "/close", db_session, staff)

    await db_session.refresh(ticket)
    assert ticket.status is TicketStatus.closed
    assert "ticket_closed" in await _kinds(db_session)
    assert wake_ups == ["outbox"]
    assert _answers(telegram)[-1] == support_handlers.CONFIRM_CLOSED.format(id=ticket.id)


async def test_close_silent_leaves_the_person_alone(db_session: AsyncSession) -> None:
    """Тихое закрытие для разговора, кончившегося ничем: писать не о чем."""
    ticket = await _ticket_in_topic(db_session)
    staff = await _staff(db_session)
    telegram = RecordingSession()

    await _command(
        Bot(token="123456:test-token", session=telegram), "/close_silent", db_session, staff
    )

    await db_session.refresh(ticket)
    assert ticket.status is TicketStatus.closed
    assert "ticket_closed" not in await _kinds(db_session)
    assert _answers(telegram)[-1] == support_handlers.CONFIRM_CLOSED_SILENT.format(id=ticket.id)


async def test_closing_from_the_topic_names_who_did_it(db_session: AsyncSession) -> None:
    """Журнал закрытий нужен для спора «моё обращение закрыли, не ответив».

    Пишет его вызывающий, а не сервис: закрытие из кабинета делает сам
    человек, и записывать его как действие персонала было бы неправдой.
    """
    ticket = await _ticket_in_topic(db_session)
    staff = await _staff(db_session)
    telegram = RecordingSession()

    await _command(Bot(token="123456:test-token", session=telegram), "/close", db_session, staff)

    record = await db_session.scalar(select(AuditLog).where(AuditLog.action == "ticket.close"))
    assert record is not None
    assert record.actor_id == staff.id
    assert record.entity_id == str(ticket.id)


async def test_mute_closes_the_conversation_and_unmute_opens_it(db_session: AsyncSession) -> None:
    """Заглушение закрывает разговор, оставляя подписку и оплату нетронутыми."""
    ticket = await _ticket_in_topic(db_session)
    person = await db_session.get(User, ticket.user_id)
    assert person is not None
    staff = await _staff(db_session)
    telegram = RecordingSession()
    bot = Bot(token="123456:test-token", session=telegram)

    await _command(bot, "/mute", db_session, staff)
    await db_session.refresh(person)
    muted = person.support_muted_at
    await _command(bot, "/unmute", db_session, staff)
    await db_session.refresh(person)

    assert muted is not None
    assert person.support_muted_at is None
    assert _answers(telegram) == [support_handlers.CONFIRM_MUTED, support_handlers.CONFIRM_UNMUTED]


async def test_repeating_a_command_admits_it_changed_nothing(db_session: AsyncSession) -> None:
    """Ложное подтверждение хуже отказа: сотрудник решил бы, что запрет снят.

    Проверяются обе стороны повтора — закрытие уже закрытого и заглушение уже
    заглушённого: у первого состояние в обращении, у второго в аккаунте.
    """
    ticket = await _ticket_in_topic(db_session)
    staff = await _staff(db_session)
    telegram = RecordingSession()
    bot = Bot(token="123456:test-token", session=telegram)

    await _command(bot, "/mute", db_session, staff)
    await _command(bot, "/mute", db_session, staff)
    await _command(bot, "/close", db_session, staff)
    await _command(bot, "/close", db_session, staff)

    await db_session.refresh(ticket)
    assert _answers(telegram)[1] == support_handlers.ALREADY_MUTED
    assert _answers(telegram)[3] == support_handlers.ALREADY_CLOSED
    assert len(await _kinds(db_session)) == 1


async def test_ban_blocks_the_account_and_closes_the_ticket_silently(
    db_session: AsyncSession,
) -> None:
    """Отвечать заблокированному некому, поэтому закрытие молчит.

    Автор решения пишется в журнал: спор «за что меня заблокировали» разбирают
    именно по нему.
    """
    ticket = await _ticket_in_topic(db_session)
    person = await db_session.get(User, ticket.user_id)
    assert person is not None
    staff = await _staff(db_session)
    telegram = RecordingSession()

    await _command(Bot(token="123456:test-token", session=telegram), "/ban", db_session, staff)

    await db_session.refresh(ticket)
    await db_session.refresh(person)
    record = await db_session.scalar(select(AuditLog).where(AuditLog.action == "user.ban"))
    assert person.status is UserStatus.banned
    assert ticket.status is TicketStatus.closed
    assert "ticket_closed" not in await _kinds(db_session)
    assert record is not None
    assert record.actor_id == staff.id
    assert _answers(telegram)[-1] == support_handlers.CONFIRM_BANNED.format(id=ticket.id)


async def test_ban_refuses_to_touch_a_colleague(db_session: AsyncSession) -> None:
    """Иначе одной командой из рабочего чата гасится доступ сотрудника."""
    ticket = await _ticket_in_topic(db_session)
    person = await db_session.get(User, ticket.user_id)
    assert person is not None
    person.role = UserRole.support
    await db_session.commit()
    staff = await _staff(db_session)
    telegram = RecordingSession()

    await _command(Bot(token="123456:test-token", session=telegram), "/ban", db_session, staff)

    await db_session.refresh(ticket)
    await db_session.refresh(person)
    assert person.status is UserStatus.active
    assert ticket.status is TicketStatus.waiting_staff
    assert _answers(telegram)[-1] == support_handlers.STAFF_IMMUNE


async def test_unban_returns_the_account_and_refuses_on_a_free_one(
    db_session: AsyncSession,
) -> None:
    """Разбан — обратный ход бана, а не подтверждение чего попало."""
    ticket = await _ticket_in_topic(db_session)
    person = await db_session.get(User, ticket.user_id)
    assert person is not None
    staff = await _staff(db_session)
    telegram = RecordingSession()
    bot = Bot(token="123456:test-token", session=telegram)

    await _command(bot, "/ban", db_session, staff)
    await _command(bot, "/unban", db_session, staff)
    await db_session.refresh(person)
    first = person.status
    await _command(bot, "/unban", db_session, staff)

    assert first is UserStatus.active
    assert _answers(telegram)[1] == support_handlers.CONFIRM_UNBANNED
    assert _answers(telegram)[2] == support_handlers.NOT_BANNED


async def test_no_command_text_ever_reaches_the_person(db_session: AsyncSession) -> None:
    """Команды регистрируются до обработчика обычных сообщений.

    Иначе «/mute» уходит человеку ответом поддержки — и вместо запрета он
    получает бессмысленную реплику.
    """
    ticket = await _ticket_in_topic(db_session)
    staff = await _staff(db_session)
    bot = Bot(token="123456:test-token", session=RecordingSession())

    for text in ("/info", "/close", "/close_silent", "/mute", "/unmute", "/ban", "/unban"):
        await _command(bot, text, db_session, staff)

    thread = await SupportService(db_session).thread(ticket.id)
    assert [message.body for message in thread if message.author_kind is TicketAuthor.staff] == []


def test_support_router_appears_only_with_a_supergroup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без супергруппы команды `/support` быть не должно: ответить некому."""
    monkeypatch.delenv("SUPPORT_CHAT_ID", raising=False)
    get_settings.cache_clear()
    without = build_dispatcher(MemoryStorage())

    monkeypatch.setenv("SUPPORT_CHAT_ID", str(SUPPORT_CHAT_ID))
    get_settings.cache_clear()
    with_chat = build_dispatcher(MemoryStorage())
    get_settings.cache_clear()

    assert not any(router.name == "support" for router in without.sub_routers)
    assert any(router.name == "support" for router in with_chat.sub_routers)
