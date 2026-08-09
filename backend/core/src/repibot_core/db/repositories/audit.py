"""Запись в журнал действий."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        action: str,
        entity: str,
        *,
        actor_id: int | None = None,
        entity_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip: str | None = None,
    ) -> None:
        self._session.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                before=before,
                after=after,
                ip=ip,
            )
        )
        await self._session.flush()

    async def compensation_with_key(self, order_id: int, idempotency_key: str) -> AuditLog | None:
        """Find a prior compensation while its order row is locked by the caller."""
        statement = select(AuditLog).where(
            AuditLog.action == "order.compensation",
            AuditLog.entity == "order",
            AuditLog.entity_id == str(order_id),
            AuditLog.after["idempotency_key"].astext == idempotency_key,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()
