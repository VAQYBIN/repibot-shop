"""Устройства и трафик глазами клиента."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient

from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker


def _panel_user_id(panel: FakePanel) -> int:
    """Триал завёл ровно одного пользователя в тестовой панели."""
    return next(iter(panel.users))


async def test_devices_need_subscription(
    api_client: AsyncClient, telegram_user_headers: dict[str, str]
) -> None:
    """Без подписки устройств нет — это 404, а не пустой список."""
    response = await api_client.get("/api/me/devices", headers=telegram_user_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "subscription_missing"


async def test_devices_are_listed_with_limit(
    api_client: AsyncClient,
    fake_panel: FakePanel,
    telegram_user_headers: dict[str, str],
    trial_subscriber: str,
) -> None:
    panel_id = _panel_user_id(fake_panel)
    fake_panel.add_device(
        panel_id,
        "laptop-hwid",
        platform="windows",
        os_version="11.0",
        device_model="ThinkPad X1 Carbon",
    )

    response = await api_client.get("/api/me/devices", headers=telegram_user_headers)
    assert response.status_code == 200
    assert response.json() == {
        "devices": [
            {
                "hwid": "laptop-hwid",
                "platform": "windows",
                "device_model": "ThinkPad X1 Carbon",
                "os_version": "11.0",
                "created_at": fake_panel.devices[panel_id][0]["createdAt"],
            }
        ],
        "limit": 3,
        "used": 1,
    }


async def test_successful_unlink_is_absent_from_next_list(
    api_client: AsyncClient,
    fake_panel: FakePanel,
    telegram_user_headers: dict[str, str],
    trial_subscriber: str,
) -> None:
    panel_id = _panel_user_id(fake_panel)
    fake_panel.add_device(panel_id, "old-phone")

    assert (await api_client.get("/api/me/devices", headers=telegram_user_headers)).json()[
        "used"
    ] == 1
    unlinked = await api_client.post(
        "/api/me/devices/unlink", json={"hwid": "old-phone"}, headers=telegram_user_headers
    )
    assert unlinked.status_code == 204

    listed = await api_client.get("/api/me/devices", headers=telegram_user_headers)
    assert listed.status_code == 200
    assert listed.json() == {"devices": [], "limit": 3, "used": 0}


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
    api_client: AsyncClient,
    fake_panel: FakePanel,
    telegram_user_headers: dict[str, str],
    trial_subscriber: str,
) -> None:
    panel_id = _panel_user_id(fake_panel)
    fake_panel.users[panel_id]["userTraffic"]["usedTrafficBytes"] = 1_024
    fake_panel.users[panel_id]["userTraffic"]["lifetimeUsedTrafficBytes"] = 8_192
    day = datetime.now(UTC).date().isoformat()
    fake_panel.add_usage(panel_id, day, 512)

    response = await api_client.get("/api/me/traffic", headers=telegram_user_headers)
    assert response.status_code == 200
    assert response.json() == {
        "used_bytes": 1_024,
        "lifetime_bytes": 8_192,
        "limit_bytes": 0,
        "days": [{"day": day, "used_bytes": 512}],
    }


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("get", "/api/me/devices", {}),
        ("post", "/api/me/devices/unlink", {"json": {"hwid": "phone"}}),
        ("get", "/api/me/traffic", {}),
    ],
)
async def test_panel_unavailable_is_503(
    api_client: AsyncClient,
    fake_panel: FakePanel,
    telegram_user_headers: dict[str, str],
    trial_subscriber: str,
    method: str,
    path: str,
    request_kwargs: dict[str, Any],
) -> None:
    fake_panel.fail_next()

    response = await getattr(api_client, method)(
        path, headers=telegram_user_headers, **request_kwargs
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "panel_unavailable"


async def test_anonymous_sees_nothing(api_client: AsyncClient) -> None:
    assert (await api_client.get("/api/me/devices")).status_code == 401
    assert (await api_client.get("/api/me/traffic")).status_code == 401
