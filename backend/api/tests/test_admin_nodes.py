"""Ноды панели через админское API: права, состав ответа и молчащая панель."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from httpx import AsyncClient

from repibot_core.integrations.remnawave.client import RemnawaveClient

pytestmark = pytest.mark.docker

# Поля, которые мы обещаем показать. Список объявлен в тесте отдельно от схемы:
# сверка схемы с самой собой не поймала бы лишнее поле, а именно лишнее поле
# здесь и опасно.
EXPECTED_FIELDS = {
    "name",
    "country_code",
    "address",
    "port",
    "is_connected",
    "is_disabled",
    "users_online",
    "traffic_used_bytes",
    "traffic_limit_bytes",
    "xray_uptime_seconds",
    "last_status_message",
}

NODE: dict[str, Any] = {
    "uuid": "33333333-3333-4333-8333-333333333333",
    "id": 1,
    "name": "Амстердам",
    "address": "10.0.0.1",
    "port": 2222,
    # Ссылка с логином и паролем прокси — то самое, чему в браузере
    # администратора делать нечего.
    "proxyUrl": "https://admin:s3cret@10.0.0.1:2222",
    "isConnected": True,
    "isDisabled": False,
    "isConnecting": False,
    "lastStatusChange": "2026-08-12T10:00:00Z",
    "lastStatusMessage": "нода на связи",
    "isTrafficTrackingActive": False,
    "trafficResetDay": None,
    "trafficLimitBytes": 0,
    "trafficUsedBytes": 1024,
    "notifyPercent": None,
    "viewPosition": 0,
    "countryCode": "NL",
    "consumptionMultiplier": 1.0,
    "nodeConsumptionMultiplier": 1.0,
    "tags": [],
    "createdAt": "2026-08-01T10:00:00Z",
    "updatedAt": "2026-08-12T10:00:00Z",
    "configProfile": {
        "activeConfigProfileUuid": "44444444-4444-4444-8444-444444444444",
        "activeInbounds": [
            {
                "uuid": "55555555-5555-4555-8555-555555555555",
                "profileUuid": "44444444-4444-4444-8444-444444444444",
                "tag": "VLESS",
                "type": "vless",
                "network": "tcp",
                "security": "reality",
                "port": 443,
                # Ключи Reality живут именно здесь: приватный ключ узла
                # уезжает в браузер вместе с любым «пробросом ответа как есть».
                "rawInbound": {"privateKey": "секретный ключ узла"},
            }
        ],
    },
    "providerUuid": None,
    "provider": None,
    "activePluginUuid": None,
    "system": None,
    "versions": None,
    "xrayUptime": 3600,
    "usersOnline": 7,
    "note": "внутренняя заметка",
}


def _panel(handler: Any) -> Any:
    """Фабрика клиента панели поверх заданной заглушки транспорта.

    Одна попытка: тесту на молчащую панель незачем ждать три захода с
    экспоненциальной задержкой.
    """

    def factory() -> RemnawaveClient:
        return RemnawaveClient(
            base_url="https://panel.example.org",
            token="token",
            max_attempts=1,
            transport=httpx.MockTransport(handler),
        )

    return factory


def _serving(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"response": [NODE]})


def _silent(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("панель не отвечает", request=request)


def _use_panel(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    from repibot_api.routers.admin import nodes

    monkeypatch.setattr(nodes, "panel_client", _panel(handler))


async def test_support_does_not_see_the_nodes(
    api_client: AsyncClient, support_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Узлы — инфраструктура, а не работа с людьми."""
    _use_panel(monkeypatch, _serving)

    # Роль проверяется явно: без этого тест проходил бы и с обычным
    # пользователем, то есть проверял бы не то ограничение.
    whoami = await api_client.get("/api/admin/whoami", headers=support_headers)
    assert whoami.json()["role"] == "support"

    response = await api_client.get("/api/admin/nodes", headers=support_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_response_carries_no_panel_secrets(
    api_client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ответ панели несёт ключи узла: пробросить его целиком — значит отдать
    их браузеру."""
    _use_panel(monkeypatch, _serving)

    response = await api_client.get("/api/admin/nodes", headers=admin_headers)

    assert response.status_code == 200
    node = response.json()[0]
    assert set(node) == EXPECTED_FIELDS
    assert "секретный ключ узла" not in response.text
    assert "s3cret" not in response.text


async def test_shown_values_come_from_the_panel(
    api_client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Урезание ответа не должно превращаться в потерю показываемого."""
    _use_panel(monkeypatch, _serving)

    node = (await api_client.get("/api/admin/nodes", headers=admin_headers)).json()[0]

    assert node["name"] == "Амстердам"
    assert node["country_code"] == "NL"
    assert node["address"] == "10.0.0.1"
    assert node["port"] == 2222
    assert node["is_connected"] is True
    assert node["is_disabled"] is False
    assert node["users_online"] == 7
    assert node["traffic_used_bytes"] == 1024
    assert node["traffic_limit_bytes"] == 0
    assert node["xray_uptime_seconds"] == 3600
    assert node["last_status_message"] == "нода на связи"


async def test_silent_panel_is_reported_not_hidden(
    api_client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пустая таблица вместо ответа читалась бы как «узлов нет» — а узлы есть,
    молчит панель."""
    _use_panel(monkeypatch, _silent)

    response = await api_client.get("/api/admin/nodes", headers=admin_headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "panel_unavailable"
