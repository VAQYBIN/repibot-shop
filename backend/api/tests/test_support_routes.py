"""Обращения в поддержку глазами клиента: кабинет и Mini App ходят сюда."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_api.routers import support
from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import Ticket
from repibot_core.ratelimit import Rule
from repibot_core.services.support import SupportService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

# Любой отрицательный номер супергруппы: наружу он не уходит, но включает
# поддержку целиком — сервис смотрит только на его наличие.
SUPPORT_CHAT_ID = "-1001234567890"
# Тема супергруппы и Telegram сотрудника, отвечающего из неё.
TOPIC_ID = 4242
STAFF_TELEGRAM_ID = 900_002


@pytest.fixture
def support_enabled(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Стенд с супергруппой.

    Настройки закэшированы, поэтому кэш сбрасывается дважды: перед тестом —
    чтобы супергруппу увидели маршруты, после — чтобы её не унаследовал
    следующий тест.
    """
    monkeypatch.setenv("SUPPORT_CHAT_ID", SUPPORT_CHAT_ID)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def without_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    """Снимает паузу между сообщениями одного человека.

    Пауза проверяется отдельным тестом. Здесь она мешала бы разыграть разговор
    в один приём: настоящие десять секунд ожидания стоили бы столько же в
    каждом прогоне набора.
    """
    monkeypatch.setattr(
        support, "TICKET_MESSAGE_PER_USER", Rule(limit=100, window=timedelta(seconds=10))
    )


async def _open(client: AsyncClient, headers: dict[str, str], body: str = "не открывается") -> int:
    response = await client.post("/api/support/tickets", headers=headers, json={"body": body})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def _staff_reply(engine: AsyncEngine, ticket_id: int, body: str) -> None:
    """Ответ сотрудника приходит из топика, а не через клиентские маршруты.

    Номер темы проставляется здесь же: в бою его записывает разбор очереди
    после создания топика, и без него ответ не находит своё обращение.
    """
    async with create_session_factory(engine)() as session:
        ticket = await session.get(Ticket, ticket_id)
        assert ticket is not None
        ticket.telegram_topic_id = TOPIC_ID
        await session.flush()
        await SupportService(session).reply_from_staff(
            TOPIC_ID, body, telegram_id=STAFF_TELEGRAM_ID, message_id=1
        )
        await session.commit()


async def test_ticket_round_trip(
    api_client: AsyncClient, user_headers: dict[str, str], support_enabled: None
) -> None:
    created = await api_client.post(
        "/api/support/tickets", headers=user_headers, json={"body": "не открывается"}
    )
    listed = await api_client.get("/api/support/tickets", headers=user_headers)

    assert created.status_code == 201
    assert [item["status"] for item in listed.json()] == ["waiting_staff"]


async def test_support_is_off_without_a_supergroup(
    api_client: AsyncClient, user_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стенд без супергруппы обязан подниматься и честно отвечать отказом."""
    monkeypatch.delenv("SUPPORT_CHAT_ID", raising=False)
    get_settings.cache_clear()

    response = await api_client.post(
        "/api/support/tickets", headers=user_headers, json={"body": "привет"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "support_unavailable"
    get_settings.cache_clear()


async def test_thread_shows_both_sides(
    api_client: AsyncClient,
    engine: AsyncEngine,
    user_headers: dict[str, str],
    support_enabled: None,
) -> None:
    """Ответ из супергруппы человек читает в кабинете, а не в Telegram."""
    ticket_id = await _open(api_client, user_headers)
    await _staff_reply(engine, ticket_id, "уже смотрим")

    response = await api_client.get(f"/api/support/tickets/{ticket_id}", headers=user_headers)

    body = response.json()
    assert response.status_code == 200
    assert [message["author"] for message in body["messages"]] == ["user", "staff"]
    assert body["messages"][1]["body"] == "уже смотрим"
    assert body["ticket"]["status"] == "waiting_user"
    assert body["ticket"]["last_staff_message_at"] is not None


async def test_reply_returns_the_move_to_staff(
    api_client: AsyncClient,
    engine: AsyncEngine,
    user_headers: dict[str, str],
    support_enabled: None,
    without_pause: None,
) -> None:
    ticket_id = await _open(api_client, user_headers)
    await _staff_reply(engine, ticket_id, "какая ошибка на экране?")

    replied = await api_client.post(
        f"/api/support/tickets/{ticket_id}/messages",
        headers=user_headers,
        json={"body": "чёрный экран"},
    )
    thread = await api_client.get(f"/api/support/tickets/{ticket_id}", headers=user_headers)

    assert replied.status_code == 201
    assert replied.json()["author"] == "user"
    assert thread.json()["ticket"]["status"] == "waiting_staff"


async def test_someone_elses_ticket_is_hidden(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    telegram_user_headers: dict[str, str],
    support_enabled: None,
) -> None:
    """Перебором номеров чужая переписка не читается и не продолжается.

    Ответ на чужой номер такой же, как на несуществующий: разница сама
    сообщала бы, что обращение с таким номером есть.
    """
    ticket_id = await _open(api_client, user_headers)

    read = await api_client.get(f"/api/support/tickets/{ticket_id}", headers=telegram_user_headers)
    replied = await api_client.post(
        f"/api/support/tickets/{ticket_id}/messages",
        headers=telegram_user_headers,
        json={"body": "а что тут?"},
    )
    closed = await api_client.post(
        f"/api/support/tickets/{ticket_id}/close", headers=telegram_user_headers
    )
    missing = await api_client.get("/api/support/tickets/999999", headers=user_headers)

    assert read.status_code == 404
    assert replied.status_code == 404
    assert closed.status_code == 404
    assert missing.status_code == 404
    assert read.json()["error"]["code"] == "not_found"


async def test_closed_ticket_refuses_the_reply(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    support_enabled: None,
    without_pause: None,
) -> None:
    """Закрытое обращение не воскресает сообщением: топика для него уже нет."""
    ticket_id = await _open(api_client, user_headers)

    closed = await api_client.post(f"/api/support/tickets/{ticket_id}/close", headers=user_headers)
    replied = await api_client.post(
        f"/api/support/tickets/{ticket_id}/messages",
        headers=user_headers,
        json={"body": "ещё вопрос"},
    )

    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert replied.status_code == 409
    assert replied.json()["error"]["code"] == "ticket_closed"


async def test_second_message_in_a_row_is_refused(
    api_client: AsyncClient, user_headers: dict[str, str], support_enabled: None
) -> None:
    """Пауза отсекает скрипт, набивающий супергруппу быстрее, чем её читают."""
    await _open(api_client, user_headers)

    response = await api_client.post(
        "/api/support/tickets", headers=user_headers, json={"body": "и ещё раз"}
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    # Без Retry-After клиент повторяет немедленно и упирается в тот же отказ.
    assert int(response.headers["retry-after"]) > 0


async def test_support_requires_signing_in(api_client: AsyncClient) -> None:
    """Переписка привязана к аккаунту: без входа неизвестно, чью показывать."""
    response = await api_client.get("/api/support/tickets")

    assert response.status_code == 401
