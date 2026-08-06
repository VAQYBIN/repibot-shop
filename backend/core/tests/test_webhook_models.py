"""Схема журналов вебхуков и расхождений."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction, ReconciliationFinding, WebhookEvent, WebhookSource

pytestmark = pytest.mark.docker


async def test_same_event_cannot_be_stored_twice(db_session: AsyncSession) -> None:
    """Повторная доставка не должна обрабатываться дважды."""
    for _ in range(2):
        db_session.add(
            WebhookEvent(
                source=WebhookSource.remnawave,
                event_id="user.expired:2026-08-06T12:00:00Z:42",
                event="user.expired",
                payload={"scope": "user"},
                received_at=datetime.now(UTC),
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_same_event_id_from_other_source_is_allowed(db_session: AsyncSession) -> None:
    """Идентификаторы источников независимы: совпадение строк — совпадение, а не дубль."""
    for source in (WebhookSource.remnawave, WebhookSource.yookassa):
        db_session.add(
            WebhookEvent(
                source=source,
                event_id="одинаковая-строка",
                event="что-то",
                payload={},
                received_at=datetime.now(UTC),
            )
        )
    await db_session.flush()


async def test_finding_records_both_sides(db_session: AsyncSession) -> None:
    """Расхождение бесполезно без обеих сторон: непонятно, что с чем разошлось."""
    finding = ReconciliationFinding(
        run_id="0f6a1c2e-0000-4000-8000-000000000001",
        user_id=None,
        field="expireAt",
        ours="2026-09-06T12:00:00+00:00",
        theirs="2026-10-06T12:00:00+00:00",
        action=FindingAction.fixed,
        created_at=datetime.now(UTC),
    )
    db_session.add(finding)
    await db_session.flush()
    assert finding.id > 0
