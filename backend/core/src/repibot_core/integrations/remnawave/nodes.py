"""Ноды панели — узлы, через которые ходит трафик подписчиков.

Только чтение: включением, перезапуском и сбросом трафика узлов занимается
сама панель, и дублировать это у себя незачем.
"""

from __future__ import annotations

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import GetNodesResponseDto
from repibot_core.integrations.remnawave.types import PanelNode


class PanelNodes:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def list(self) -> list[PanelNode]:
        response = await self._client.request("GET", "/api/nodes")
        if response.status_code >= httpx.codes.BAD_REQUEST:
            # Отказ поднимается исключением, а не превращается в пустой список:
            # пустой список читается как «узлов нет», то есть как авария.
            raise RemnawaveRejected(response.status_code, response.text[:500])
        parsed = GetNodesResponseDto.model_validate_json(response.content)
        # Обёртку response разворачиваем здесь: наружу уходит список нод, а не
        # форма ответа панели.
        return list(parsed.response)
