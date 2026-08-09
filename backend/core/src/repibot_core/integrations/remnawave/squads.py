"""Внутренние сквады панели — то, из чего собирается тариф."""

from __future__ import annotations

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import GetInternalSquadsResponseDto
from repibot_core.integrations.remnawave.types import PanelSquad


class PanelSquads:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def list(self) -> list[PanelSquad]:
        response = await self._client.request("GET", "/api/internal-squads")
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
        parsed = GetInternalSquadsResponseDto.model_validate_json(response.content)
        # Обёртку response.internalSquads разворачиваем здесь: наружу уходит
        # список сквадов, а не форма ответа панели.
        return list(parsed.response.internalSquads)
