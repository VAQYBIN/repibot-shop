"""Идемпотентность приёма и чтение последнего прогона сверки."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction, WebhookSource
from repibot_core.db.repositories.reconciliation import FindingRepository
from repibot_core.db.repositories.webhooks import WebhookRepository

pytestmark = pytest.mark.docker

RUN_ONE = "0f6a1c2e-0000-4000-8000-000000000001"
RUN_TWO = "0f6a1c2e-0000-4000-8000-000000000002"


async def test_second_delivery_returns_none(db_session: AsyncSession) -> None:
    """Повторная доставка не должна порождать вторую обработку."""
    repository = WebhookRepository(db_session)
    now = datetime.now(UTC)

    first = await repository.remember(
        source=WebhookSource.remnawave,
        event_id="user.expired:2026-08-06T12:00:00Z:42",
        event="user.expired",
        payload={"scope": "user"},
        now=now,
    )
    second = await repository.remember(
        source=WebhookSource.remnawave,
        event_id="user.expired:2026-08-06T12:00:00Z:42",
        event="user.expired",
        payload={"scope": "user"},
        now=now,
    )

    assert first is not None
    assert second is None


async def test_latest_run_returns_only_last(db_session: AsyncSession) -> None:
    """Отчёт читается прогоном целиком: смешанная лента не отвечает ни на что."""
    findings = FindingRepository(db_session)
    now = datetime.now(UTC)
    for run in (RUN_ONE, RUN_TWO):
        await findings.add(
            run_id=run,
            user_id=None,
            field="expireAt",
            ours="a",
            theirs="b",
            action=FindingAction.fixed,
            now=now,
        )

    rows = await findings.latest_run()
    assert [row.run_id for row in rows] == [RUN_TWO]
