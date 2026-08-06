"""Фасады панели: адреса, тела запросов и разбор ответов."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from repibot_core.integrations.remnawave.client import RemnawaveClient
from repibot_core.integrations.remnawave.squads import PanelSquads
from repibot_core.integrations.remnawave.types import CreateUserBody
from repibot_core.integrations.remnawave.users import PanelUsers

USER_PAYLOAD: dict[str, Any] = {
    "id": 42,
    "shortUuid": "abc123",
    "username": "rp_1",
    "status": "ACTIVE",
    "trafficLimitBytes": 0,
    "trafficLimitStrategy": "NO_RESET",
    "expireAt": "2026-09-06T12:00:00Z",
    "telegramId": None,
    "email": None,
    "description": None,
    "tag": "REPIBOT",
    "hwidDeviceLimit": 3,
    "externalSquadUuid": None,
    "trojanPassword": "trojan-password",
    "vlessUuid": "11111111-1111-4111-8111-111111111111",
    "ssPassword": "ss-password",
    "lastTriggeredThreshold": 0,
    "subRevokedAt": None,
    "lastTrafficResetAt": None,
    "createdAt": "2026-08-06T12:00:00Z",
    "updatedAt": "2026-08-06T12:00:00Z",
    "subscriptionUrl": "https://panel.example.org/sub/abc123",
    "activeInternalSquads": [],
    "userTraffic": {
        "usedTrafficBytes": 0,
        "lifetimeUsedTrafficBytes": 0,
        "onlineAt": "2026-08-06T12:00:00Z",
        "firstConnectedAt": "2026-08-06T12:00:00Z",
        "lastConnectedNodeUuid": "22222222-2222-4222-8222-222222222222",
    },
}


def _client(handler: httpx.MockTransport) -> RemnawaveClient:
    return RemnawaveClient(base_url="https://panel.example.org", token="token", transport=handler)


async def test_user_with_null_fields_parses() -> None:
    """Панель присылает null в telegramId, email и tag — разбор не должен падать."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"response": USER_PAYLOAD})
    )
    user = await PanelUsers(_client(transport)).get(42)

    assert user is not None
    assert user.telegramId is None
    assert user.subscriptionUrl.endswith("/sub/abc123")


async def test_missing_user_is_none_not_error() -> None:
    """404 — обычный ответ «такого нет», а не отказ панели."""
    transport = httpx.MockTransport(lambda request: httpx.Response(404, json={}))
    assert await PanelUsers(_client(transport)).get(42) is None


async def test_resolve_sends_only_given_key() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"response": USER_PAYLOAD})

    await PanelUsers(_client(httpx.MockTransport(handler))).resolve(username="rp_1")

    assert seen["url"] == "https://panel.example.org/api/users/resolve"
    assert seen["body"] == '{"username":"rp_1"}'


async def test_update_goes_to_collection_with_id_in_body() -> None:
    """В 3.2.1 PATCH идёт на /api/users, идентификатор — в теле."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"response": USER_PAYLOAD})

    from repibot_core.integrations.remnawave.types import UpdateUserBody

    await PanelUsers(_client(httpx.MockTransport(handler))).update(
        UpdateUserBody(id=42, hwidDeviceLimit=5)
    )

    assert seen["method"] == "PATCH"
    assert seen["url"] == "https://panel.example.org/api/users"
    assert '"id":42' in seen["body"]
    assert '"hwidDeviceLimit":5' in seen["body"]


async def test_update_sends_only_what_caller_set() -> None:
    """PATCH не должен править поля, которых вызывающий не касался.

    У trafficLimitStrategy в схеме панели значение по умолчанию «NO_RESET»,
    а не null, поэтому exclude_none его не отсекает: обновление одного лимита
    устройств молча сбрасывало бы пользователю стратегию сброса трафика.
    """
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"response": USER_PAYLOAD})

    from repibot_core.integrations.remnawave.types import UpdateUserBody

    await PanelUsers(_client(httpx.MockTransport(handler))).update(
        UpdateUserBody(id=42, hwidDeviceLimit=5)
    )

    assert "trafficLimitStrategy" not in seen["body"]
    assert "status" not in seen["body"]


async def test_create_raises_on_rejection() -> None:
    """400 от панели — наша ошибка запроса, её нельзя проглотить."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(400, json={"message": "username taken"})
    )
    with pytest.raises(Exception, match="400"):
        await PanelUsers(_client(transport)).create(
            CreateUserBody(username="rp_1", expireAt=datetime(2026, 9, 6, 12, tzinfo=UTC))
        )


async def test_squads_are_flattened() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "response": {
                    "total": 1,
                    "internalSquads": [
                        {
                            "uuid": "11111111-1111-4111-8111-111111111111",
                            "viewPosition": 0,
                            "name": "Европа",
                            "info": {"membersCount": 0, "inboundsCount": 1},
                            "inbounds": [],
                            "createdAt": "2026-08-06T12:00:00Z",
                            "updatedAt": "2026-08-06T12:00:00Z",
                        }
                    ],
                }
            },
        )
    )
    squads = await PanelSquads(_client(transport)).list()
    assert [squad.name for squad in squads] == ["Европа"]
