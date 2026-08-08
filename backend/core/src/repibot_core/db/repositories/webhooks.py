"""Доступ к принятым вебхукам."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert
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

        Один INSERT с ON CONFLICT не оставляет проигравшую транзакцию в
        состоянии отката. Разделённые SELECT и INSERT позволяли двум
        одновременным доставкам увидеть отсутствие строки и столкнуться на
        уникальном индексе.
        """
        statement = (
            insert(WebhookEvent)
            .values(
                source=source,
                event_id=event_id,
                event=event,
                payload=payload,
                received_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_webhook_events_source_id")
            .returning(WebhookEvent)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def mark_processed(self, event: WebhookEvent, now: datetime) -> None:
        """Отмечает событие разобранным.

        Отметка ставится отдельным шагом, а не при приёме: пустое значение
        означает «приняли, но обработать не успели», и по нему видно, что
        осталось разобрать после сбоя обработчика.
        """
        event.processed_at = now
        await self._session.flush()
