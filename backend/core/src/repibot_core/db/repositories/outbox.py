"""Доступ к очереди надёжной доставки."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import OutboxMessage


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, topic: str, payload: dict[str, Any], *, available_at: datetime | None = None
    ) -> OutboxMessage:
        message = OutboxMessage(topic=topic, payload=payload)
        if available_at is not None:
            message.available_at = available_at
        self._session.add(message)
        await self._session.flush()
        return message

    async def take_batch(self, *, limit: int, now: datetime) -> list[OutboxMessage]:
        """Забирает готовые сообщения, пропуская занятые другим воркером.

        SKIP LOCKED вместо ожидания блокировки: два воркера должны разбирать
        очередь параллельно, а не стоять в очереди друг за другом.
        """
        statement = (
            select(OutboxMessage)
            .where(OutboxMessage.processed_at.is_(None), OutboxMessage.available_at <= now)
            .order_by(OutboxMessage.available_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(statement)).scalars())

    async def mark_processed(self, message: OutboxMessage) -> None:
        message.processed_at = datetime.now(UTC)
        await self._session.flush()

    async def postpone(self, message: OutboxMessage, error: str, delay: timedelta) -> None:
        message.attempts += 1
        message.last_error = error[:1000]
        message.available_at = datetime.now(UTC) + delay
        await self._session.flush()
