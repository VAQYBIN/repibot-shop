"""Топики супергруппы: клиент Bot API и разбор темы `support.outbound`."""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import User
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.integrations.telegram.support_chat import SupportChat
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.services.support import TOPIC_SUPPORT_OUTBOUND, SupportService
from repibot_core.settings import Settings

SUPPORT_CHAT_ID = -1_001_234_567_890

Handler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


def _settings() -> Settings:
    return Settings(support_chat_id=SUPPORT_CHAT_ID)


def _chat(handler: Handler) -> SupportChat:
    return SupportChat(_settings(), httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_topic_is_created_once_and_reused() -> None:
    """Второй топик на то же обращение разорвал бы переписку надвое."""
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", maxsplit=1)[-1])
        return httpx.Response(200, json={"ok": True, "result": {"message_thread_id": 12}})

    chat = _chat(handler)
    try:
        topic_id = await chat.create_topic("Не открывается")
    finally:
        await chat.aclose()

    assert topic_id == 12
    assert calls == ["createForumTopic"]


async def test_message_goes_to_the_topic_without_parse_mode() -> None:
    """Чужой текст в топике не должен превращаться в разметку.

    С `parse_mode` сотрудник мог бы подделать служебное сообщение, а обычная
    звёздочка в ответе — уронить отправку разбором разметки.
    """
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path.rsplit("/", maxsplit=1)[-1]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})

    chat = _chat(handler)
    try:
        message_id = await chat.post(12, "*не разметка*")
    finally:
        await chat.aclose()

    assert message_id == 77
    assert seen["path"] == "sendMessage"
    assert seen["body"] == {
        "chat_id": SUPPORT_CHAT_ID,
        "message_thread_id": 12,
        "text": "*не разметка*",
    }


async def test_closing_names_the_thread() -> None:
    """Без `message_thread_id` закрылась бы не та тема."""
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path.rsplit("/", maxsplit=1)[-1]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "result": True})

    chat = _chat(handler)
    try:
        await chat.close_topic(12)
    finally:
        await chat.aclose()

    assert seen["path"] == "closeForumTopic"
    assert seen["body"] == {"chat_id": SUPPORT_CHAT_ID, "message_thread_id": 12}


async def test_refusal_of_the_supergroup_is_raised_not_swallowed() -> None:
    """Бот без права управления темами обязан оставить обращение в очереди.

    Проглоченный отказ пометил бы сообщение доставленным, и обращение
    исчезло бы, не дойдя ни до кого.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200, json={"ok": False, "description": "not enough rights to manage topics"}
        )

    chat = _chat(handler)
    try:
        with pytest.raises(RuntimeError, match="manage topics"):
            await chat.create_topic("Не открывается")
    finally:
        await chat.aclose()


# --- разбор темы support.outbound ---


def _dispatcher(factory: async_sessionmaker[AsyncSession], chat: SupportChat) -> OutboxDispatcher:
    from repibot_core.integrations.remnawave.users import PanelUsers
    from repibot_core.services.dispatcher import build_dispatcher
    from repibot_core.testing.remnawave import FakePanel

    return build_dispatcher(factory, users=PanelUsers(FakePanel().client()), support=chat)


@pytest.mark.docker
async def test_topic_id_is_stored_before_the_message_is_sent(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Идентификатор топика пишется своей транзакцией сразу после создания.

    Иначе падение на отправке даёт второй топик при повторе — и переписка
    рвётся надвое.
    """
    user = User(email=None, telegram_id=310_001, referral_code="topic001")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    ticket = await SupportService(db_session, _settings()).open(user.id, "не открывается")
    await db_session.commit()
    factory = create_session_factory(engine)
    calls: list[str] = []

    async def failing(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", maxsplit=1)[-1]
        calls.append(method)
        if method == "createForumTopic":
            return httpx.Response(200, json={"ok": True, "result": {"message_thread_id": 12}})
        return httpx.Response(200, json={"ok": False, "description": "flood wait"})

    chat = _chat(failing)
    try:
        delivered = await _dispatcher(factory, chat).process(db_session)
    finally:
        await chat.aclose()
    await db_session.refresh(ticket)

    assert delivered == 0
    assert calls == ["createForumTopic", "sendMessage"]
    assert ticket.telegram_topic_id == 12

    async def working(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", maxsplit=1)[-1])
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})

    retry = _chat(working)
    try:
        # Повтор отложен на десять секунд, поэтому пачка берётся из будущего.
        again = await _dispatcher(factory, retry).process(
            db_session, now=datetime.now(UTC) + timedelta(minutes=1)
        )
    finally:
        await retry.aclose()

    assert again == 1
    assert calls[2:] == ["sendMessage"]


@pytest.mark.docker
async def test_task_for_a_missing_ticket_is_dropped(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Удалённый вместе с аккаунтом тикет не должен вечно висеть в очереди."""
    await OutboxRepository(db_session).add(TOPIC_SUPPORT_OUTBOUND, {"ticket_id": 999_999})
    await db_session.commit()
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"ok": True, "result": {"message_thread_id": 1}})

    chat = _chat(handler)
    try:
        delivered = await _dispatcher(create_session_factory(engine), chat).process(db_session)
    finally:
        await chat.aclose()

    assert delivered == 1
    assert calls == []
