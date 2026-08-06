"""Выдача кода привязки и отвязка Telegram."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import text

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


@pytest.fixture
def bot_username(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подменяет обращение к Bot API: сети в тестах нет."""
    from repibot_api.routers import me

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {"username": "repibot_test_bot"}})

    monkeypatch.setattr(
        me, "bot_http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def _sign_in(client: AsyncClient) -> str:
    """Регистрирует человека письмом: у входа через MiniApp Telegram уже привязан."""
    await client.post(
        "/api/auth/register",
        json={"email": "user@example.org", "password": PASSWORD, "language": "ru"},
    )

    from repibot_api.deps import get_session_factory

    async with get_session_factory()() as session:
        row = await session.execute(
            text("select payload from outbox where topic = 'email.verify' order by id desc limit 1")
        )
        link = str(row.scalar_one()["link"])

    response = await client.post("/api/auth/verify-email", json={"token": link.split("token=")[1]})
    return str(response.json()["access_token"])


async def test_link_code_comes_with_a_bot_link(api_client: AsyncClient, bot_username: None) -> None:
    token = await _sign_in(api_client)

    response = await api_client.post(
        "/api/me/telegram/link-code", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["url"] == f"https://t.me/repibot_test_bot?start=link_{body['code']}"
    assert body["expires_in"] == 600


async def test_unlink_without_telegram_is_not_found(
    api_client: AsyncClient, bot_username: None
) -> None:
    token = await _sign_in(api_client)

    response = await api_client.delete(
        "/api/me/telegram", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_sixth_code_in_an_hour_is_refused(
    api_client: AsyncClient, bot_username: None
) -> None:
    """Пять кодов в час на пользователя: больше нужно только перебору."""
    token = await _sign_in(api_client)
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(5):
        issued = await api_client.post("/api/me/telegram/link-code", headers=headers)
        assert issued.status_code == 200

    response = await api_client.post("/api/me/telegram/link-code", headers=headers)

    assert response.status_code == 429
    assert response.headers["Retry-After"]
