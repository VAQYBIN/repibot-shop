"""Гейт роли. Страницы админки — подпроект 5, проверяется сам гейт."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from repibot_core.settings import get_settings
from repibot_core.testing.initdata import build_init_data

pytestmark = pytest.mark.docker


async def test_regular_user_is_refused(api_client: AsyncClient) -> None:
    login = await api_client.post(
        "/api/auth/telegram/miniapp",
        json={"init_data": build_init_data(bot_token="123456:test-token", telegram_id=555)},
    )
    token = login.json()["access_token"]

    response = await api_client.get(
        "/api/admin/whoami", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_from_env_passes_the_gate(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "999")
    get_settings.cache_clear()

    login = await api_client.post(
        "/api/auth/telegram/miniapp",
        json={"init_data": build_init_data(bot_token="123456:test-token", telegram_id=999)},
    )
    token = login.json()["access_token"]

    response = await api_client.get(
        "/api/admin/whoami", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    get_settings.cache_clear()


async def test_gate_without_token_is_401(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/admin/whoami")

    assert response.status_code == 401
