"""Устройства пользователя в панели.

Панель считает привязанные устройства сама и режет доступ при превышении
лимита тарифа. Мы их не храним — читаем и удаляем по требованию.
"""

from __future__ import annotations

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import GetUserHwidDevicesResponseDto
from repibot_core.integrations.remnawave.types import DeleteDeviceBody, PanelDevice


class PanelDevices:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def list(self, panel_id: int) -> list[PanelDevice]:
        response = await self._client.request("GET", f"/api/hwid/devices/{panel_id}")
        # 404 — «устройств нет», а не отказ: у только что созданного
        # пользователя панели их и не должно быть.
        if response.status_code == httpx.codes.NOT_FOUND:
            return []
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
        return list(
            GetUserHwidDevicesResponseDto.model_validate_json(response.content).response.devices
        )

    async def delete(self, panel_id: int, hwid: str) -> None:
        body = DeleteDeviceBody(userId=panel_id, hwid=hwid)
        response = await self._client.request(
            "POST", "/api/hwid/devices/delete", content=body.model_dump_json()
        )
        # 404 здесь не «нечего удалять», а отказ: hwid либо чужой, либо
        # выдуман, и сервис обязан отличить это от успешной отвязки.
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
