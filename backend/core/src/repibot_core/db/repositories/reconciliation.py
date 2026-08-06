"""Доступ к расхождениям сверки."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction, ReconciliationFinding


class FindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        run_id: str,
        user_id: int | None,
        field: str,
        ours: str | None,
        theirs: str | None,
        action: FindingAction,
        now: datetime,
    ) -> ReconciliationFinding:
        row = ReconciliationFinding(
            run_id=run_id,
            user_id=user_id,
            field=field,
            ours=ours,
            theirs=theirs,
            action=action,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest_run(self) -> list[ReconciliationFinding]:
        """Расхождения последнего прогона, у которого они были.

        Прогон без расхождений строк не оставляет, поэтому «последний прогон»
        определяется по последней записи, а не по времени запуска.
        """
        last = (
            select(ReconciliationFinding.run_id).order_by(ReconciliationFinding.id.desc()).limit(1)
        )
        run_id = (await self._session.execute(last)).scalar_one_or_none()
        if run_id is None:
            return []

        statement = (
            select(ReconciliationFinding)
            .where(ReconciliationFinding.run_id == run_id)
            .order_by(ReconciliationFinding.id)
        )
        return list((await self._session.execute(statement)).scalars())
