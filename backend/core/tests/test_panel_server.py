"""HTTP-обёртка вокруг заглушки панели: та же логика, но по сети."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest
from starlette.types import ASGIApp

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.integrations.remnawave.stats import PanelStats
from repibot_core.integrations.remnawave.types import CreateUserBody
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.testing.panel_server import create_panel_app


def _client(app: ASGIApp) -> RemnawaveClient:
    return RemnawaveClient(
        base_url="http://panel.test",
        token="t",
        max_attempts=1,
        transport=httpx.ASGITransport(app=app),
    )


async def test_created_user_is_readable_over_http() -> None:
    client = _client(create_panel_app())
    users = PanelUsers(client)

    created = await users.create(
        CreateUserBody(username="rp_1", expireAt=datetime(2026, 9, 6, 12, tzinfo=UTC))
    )
    found = await users.resolve(username="rp_1")

    assert found is not None
    assert found.id == created.id
    await client.aclose()


async def test_seeded_user_exposes_device_traffic_and_delete_contract() -> None:
    app = create_panel_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(base_url="http://panel.test", transport=transport) as seed_client:
        response = await seed_client.post(
            "/__seed/user",
            json={
                "username": "rp_42",
                "expireAt": "2026-09-06T12:00:00Z",
                "device": {
                    "hwid": "phone-1",
                    "platform": "android",
                    "osVersion": "15",
                    "deviceModel": "Pixel 9",
                },
                "traffic": {
                    "usedTrafficBytes": 2_048,
                    "lifetimeUsedTrafficBytes": 8_192,
                    "days": {"2026-08-07": 512, "2026-08-08": 1_536},
                },
            },
        )

    assert response.status_code == 201
    seeded = response.json()["response"]
    assert seeded["username"] == "rp_42"

    panel_client = _client(app)
    devices = PanelDevices(panel_client)
    stats = PanelStats(panel_client)

    found_devices = await devices.list(seeded["id"])
    assert [(device.hwid, device.platform, device.deviceModel) for device in found_devices] == [
        ("phone-1", "android", "Pixel 9")
    ]

    usage = await stats.usage(seeded["id"], start=date(2026, 8, 7), end=date(2026, 8, 8))
    assert usage.categories == ["2026-08-07", "2026-08-08"]
    assert usage.sparklineData == [512, 1_536]

    await devices.delete(seeded["id"], "phone-1")
    assert await devices.list(seeded["id"]) == []
    await panel_client.aclose()


async def test_seed_rejects_malformed_payload_without_mutating_panel() -> None:
    app = create_panel_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(base_url="http://panel.test", transport=transport) as client:
        response = await client.post("/__seed/user", json={"username": "rp_1"})
        resolved = await client.post("/api/users/resolve", json={"username": "rp_1"})

    assert response.status_code == 400
    assert response.json() == {"message": "invalid seed payload"}
    assert resolved.status_code == 404


async def test_separate_apps_do_not_share_users() -> None:
    first_client = _client(create_panel_app())
    second_client = _client(create_panel_app())
    first_users = PanelUsers(first_client)
    second_users = PanelUsers(second_client)
    await first_users.create(CreateUserBody(username="rp_1", expireAt="2026-09-06T12:00:00Z"))

    assert await second_users.resolve(username="rp_1") is None
    await first_client.aclose()
    await second_client.aclose()


async def test_unknown_route_and_missing_device_return_panel_errors() -> None:
    app = create_panel_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(base_url="http://panel.test", transport=transport) as client:
        unknown = await client.get("/not-a-panel-route")
        seeded = await client.post(
            "/__seed/user",
            json={"username": "rp_7", "expireAt": "2026-09-06T12:00:00Z"},
        )

    assert unknown.status_code == 404
    assert unknown.json() == {"message": "not found"}

    panel_client = _client(app)
    with pytest.raises(RemnawaveRejected) as error:
        await PanelDevices(panel_client).delete(seeded.json()["response"]["id"], "missing")
    assert error.value.status_code == 404
    await panel_client.aclose()


async def test_health_reports_ready_without_changing_panel_state() -> None:
    app = create_panel_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(base_url="http://panel.test", transport=transport) as client:
        first = await client.get("/health")
        second = await client.get("/health")

    assert first.status_code == 200
    assert first.json() == {"status": "ok"}
    assert second.status_code == 200
