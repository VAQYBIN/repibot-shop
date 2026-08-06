"""Доступ к принятым вебхукам."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import WebhookEvent, WebhookSource


class WebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def remember(
        self,
        *,
        source: WebhookSource,
        event_id: str,
        event: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> WebhookEvent | None:
        """Записывает событие. `None` — такое уже принимали.

        Проверка запросом, а не перехватом ошибки уникальности: перехват
        оставил бы транзакцию в состоянии отката, и обработчику пришлось бы
        начинать её заново ради заведомо ненужной работы.
        """
        statement = select(WebhookEvent).where(
            WebhookEvent.source == source, WebhookEvent.event_id == event_id
        )
        if (await self._session.execute(statement)).scalar_one_or_none() is not None:
            return None

        row = WebhookEvent(
            source=source, event_id=event_id, event=event, payload=payload, received_at=now
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def mark_processed(self, event: WebhookEvent, now: datetime) -> None:
        """Отмечает событие разобранным.

        Отметка ставится отдельным шагом, а не при приёме: пустое значение
        означает «приняли, но обработать не успели», и по нему видно, что
        осталось разобрать после сбоя обработчика.
        """
        event.processed_at = now
        await self._session.flush()
