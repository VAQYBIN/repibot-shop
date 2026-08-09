"""Потребление трафика по дням."""

from __future__ import annotations

from datetime import date

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import GetStatsUserUsageResponseDto
from repibot_core.integrations.remnawave.types import PanelUsage


class PanelStats:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def usage(self, panel_id: int, *, start: date, end: date) -> PanelUsage:
        """Обе границы обязательны: панель не подставляет период по умолчанию."""
        response = await self._client.request(
            "GET",
            f"/api/bandwidth-stats/users/{panel_id}",
            params={"start": start.isoformat(), "end": end.isoformat()},
        )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
        return GetStatsUserUsageResponseDto.model_validate_json(response.content).response
