"""Фасад нод панели: адрес запроса, разворот обёртки и поведение при отказе."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.nodes import PanelNodes


def _node(name: str, country: str) -> dict[str, Any]:
    """Нода со всеми обязательными полями ответа панели.

    Форма повторяет схему целиком, включая proxyUrl и uuid: тест разбора,
    собранный из удобного подмножества, прошёл бы и на модели, которая
    настоящий ответ панели не принимает.
    """
    return {
        "uuid": "33333333-3333-4333-8333-333333333333",
        "id": 1,
        "name": name,
        "address": "10.0.0.1",
        "port": 2222,
        "proxyUrl": None,
        "isConnected": True,
        "isDisabled": False,
        "isConnecting": False,
        "lastStatusChange": "2026-08-12T10:00:00Z",
        "lastStatusMessage": "нода на связи",
        "isTrafficTrackingActive": False,
        "trafficResetDay": None,
        "trafficLimitBytes": 0,
        "trafficUsedBytes": 0,
        "notifyPercent": None,
        "viewPosition": 0,
        "countryCode": country,
        "consumptionMultiplier": 1.0,
        "nodeConsumptionMultiplier": 1.0,
        "tags": [],
        "createdAt": "2026-08-01T10:00:00Z",
        "updatedAt": "2026-08-12T10:00:00Z",
        "configProfile": {"activeConfigProfileUuid": None, "activeInbounds": []},
        "providerUuid": None,
        "provider": None,
        "activePluginUuid": None,
        "system": None,
        "versions": None,
        "xrayUptime": 3600,
        "usersOnline": 7,
        "note": None,
    }


def _client(transport: httpx.MockTransport) -> RemnawaveClient:
    # Одна попытка: тесту на отказ незачем ждать три захода с задержкой.
    return RemnawaveClient(
        base_url="https://panel.example.org",
        token="token",
        max_attempts=1,
        transport=transport,
    )


async def test_nodes_are_unwrapped_from_the_panel_envelope() -> None:
    """Наружу уходит список нод, а не форма ответа панели: обёртка — деталь
    протокола, и знать о ней должен только фасад."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        return httpx.Response(
            200, json={"response": [_node("Амстердам", "NL"), _node("Франкфурт", "DE")]}
        )

    nodes = await PanelNodes(_client(httpx.MockTransport(handler))).list()

    assert seen["method"] == "GET"
    assert seen["url"] == "https://panel.example.org/api/nodes"
    assert [node.name for node in nodes] == ["Амстердам", "Франкфурт"]
    assert [node.countryCode for node in nodes] == ["NL", "DE"]


async def test_a_rejection_is_raised_not_swallowed() -> None:
    """Проглоченный отказ показал бы администратору пустой список узлов —
    то же самое, что «все ноды исчезли»."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(403, json={"message": "forbidden"})
    )

    with pytest.raises(RemnawaveRejected, match="403"):
        await PanelNodes(_client(transport)).list()
