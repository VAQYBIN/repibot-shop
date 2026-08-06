"""Профиль и сессии через API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from repibot_core.testing.initdata import build_init_data

pytestmark = pytest.mark.docker


async def _miniapp_token(client: AsyncClient, telegram_id: int = 777) -> str:
    response = await client.post(
        "/api/auth/telegram/miniapp",
        json={"init_data": build_init_data(bot_token="123456:test-token", telegram_id=telegram_id)},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


async def test_me_requires_token(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_returns_profile(api_client: AsyncClient) -> None:
    token = await _miniapp_token(api_client)

    response = await api_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert response.status_code == 200
    assert body["has_telegram"] is True
    assert body["has_password"] is False
    assert body["email"] is None
    assert body["role"] == "user"


async def test_language_is_updated(api_client: AsyncClient) -> None:
    token = await _miniapp_token(api_client)

    response = await api_client.patch(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Иван", "language": "en"},
    )

    assert response.status_code == 200
    assert response.json()["language"] == "en"


async def test_first_password_is_set_without_current(api_client: AsyncClient) -> None:
    """У вошедшего через Telegram пароля нет — спрашивать текущий не с чего."""
    token = await _miniapp_token(api_client)

    response = await api_client.post(
        "/api/me/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"new_password": "совершенно обычный пароль"},
    )

    assert response.status_code == 204


async def test_sessions_are_listed_and_revoked(api_client: AsyncClient) -> None:
    token = await _miniapp_token(api_client)
    other = await _miniapp_token(api_client)  # второе открытие MiniApp — вторая сессия
    headers = {"Authorization": f"Bearer {token}"}

    listed = await api_client.get("/api/me/sessions", headers=headers)
    assert listed.status_code == 200
    sessions = listed.json()
    assert len(sessions) == 2
    assert [item["is_current"] for item in sessions].count(True) == 1

    victim = next(item["id"] for item in sessions if not item["is_current"])
    revoked = await api_client.delete(f"/api/me/sessions/{victim}", headers=headers)
    assert revoked.status_code == 204

    # Отозванная сессия перестаёт работать немедленно, а не через 15 минут.
    denied = await api_client.get("/api/me", headers={"Authorization": f"Bearer {other}"})
    assert denied.status_code == 401


async def test_session_of_another_user_cannot_be_revoked(api_client: AsyncClient) -> None:
    mine = await _miniapp_token(api_client, telegram_id=777)
    stranger = await _miniapp_token(api_client, telegram_id=888)

    listed = await api_client.get(
        "/api/me/sessions", headers={"Authorization": f"Bearer {stranger}"}
    )
    victim = listed.json()[0]["id"]

    response = await api_client.delete(
        f"/api/me/sessions/{victim}", headers={"Authorization": f"Bearer {mine}"}
    )

    assert response.status_code == 404
