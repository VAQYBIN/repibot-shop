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
from repibot_core.db.models import Ticket, TicketAuthor, TicketMessage, TicketStatus, User
from repibot_core.services.support import SupportService
from repibot_core.settings import get_settings

SUPPORT_CHAT_ID = -1_002_000_000_001
FOREIGN_CHAT_ID = -1_002_999_999_999
TOPIC_ID = 12


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
    closed: list[tuple[int, bool]] = field(default_factory=list)

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

    async def close(self, ticket_id: int, *, by_staff: bool) -> None:
        self.closed.append((ticket_id, by_staff))

    async def list_for_user(self, user_id: int) -> list[FakeTicket]:
        return list(self.tickets)


class RecordingSession(BaseSession):
    """Bot без сети: диспетчер обязан работать, ничего никуда не отправляя."""

    async def close(self) -> None:
        return None

    async def make_request(
        self,
        bot: Bot,
        method: Any,
        timeout: int | None = None,  # noqa: ASYNC109
    ) -> Any:
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
    bot = Bot(token="123456:test-token", session=RecordingSession())

    await _support_dispatcher().feed_update(
        bot, _topic_update(is_bot=False, text="/close"), session=db_session, language="ru"
    )

    await db_session.refresh(ticket)
    thread = await SupportService(db_session).thread(ticket.id)
    assert ticket.status is TicketStatus.closed
    assert [message.author_kind for message in thread] == [TicketAuthor.user, TicketAuthor.system]


async def test_close_in_an_unknown_topic_changes_nothing(db_session: AsyncSession) -> None:
    """Чужая тема без обращения не должна ни падать, ни закрывать соседнее."""
    ticket = await _ticket_in_topic(db_session)
    bot = Bot(token="123456:test-token", session=RecordingSession())

    await _support_dispatcher().feed_update(
        bot,
        _topic_update(is_bot=False, text="/close", topic_id=TOPIC_ID + 1),
        session=db_session,
        language="ru",
    )

    await db_session.refresh(ticket)
    messages = await db_session.scalar(select(func.count()).select_from(TicketMessage))
    assert ticket.status is TicketStatus.waiting_staff
    assert messages == 1


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
