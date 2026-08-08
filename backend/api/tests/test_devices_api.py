"""Устройства и трафик глазами клиента."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker


async def test_devices_need_subscription(
    api_client: AsyncClient, telegram_user_headers: dict[str, str]
) -> None:
    """Без подписки устройств нет — это 404, а не пустой список."""
    response = await api_client.get("/api/me/devices", headers=telegram_user_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "subscription_missing"


async def test_devices_are_listed_with_limit(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_subscriber: str
) -> None:
    response = await api_client.get("/api/me/devices", headers=telegram_user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] >= 0
    assert body["used"] == len(body["devices"])


async def test_unlink_of_foreign_device_is_not_found(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_subscriber: str
) -> None:
    response = await api_client.post(
        "/api/me/devices/unlink", json={"hwid": "чужое"}, headers=telegram_user_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "device_not_found"


async def test_unlink_is_rate_limited(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_subscriber: str
) -> None:
    """Ограничение защищает не нас, а панель: без него лимит устройств обходится циклом."""
    last = None
    for _ in range(12):
        last = await api_client.post(
            "/api/me/devices/unlink", json={"hwid": "чужое"}, headers=telegram_user_headers
        )
    assert last is not None
    assert last.status_code == 429
    assert last.headers["retry-after"]


async def test_traffic_returns_limit_and_days(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_subscriber: str
) -> None:
    response = await api_client.get("/api/me/traffic", headers=telegram_user_headers)
    assert response.status_code == 200
    body = response.json()
    assert "used_bytes" in body
    assert isinstance(body["days"], list)


async def test_anonymous_sees_nothing(api_client: AsyncClient) -> None:
    assert (await api_client.get("/api/me/devices")).status_code == 401
    assert (await api_client.get("/api/me/traffic")).status_code == 401
