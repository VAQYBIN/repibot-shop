"""Выборки, на которые опираются сервисы."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.trials import TrialRepository
from repibot_core.domain.subscriptions import SubscriptionState

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


def _plan_fields(code: str, **overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "code": code,
        "name": {"ru": code, "en": code},
        "description": None,
        "duration_days": 30,
        "price_rub": Decimal("299.00"),
        "price_stars": 199,
        "traffic_limit_bytes": 0,
        "traffic_reset_strategy": TrafficResetStrategy.NO_RESET,
        "hwid_device_limit": 3,
        "internal_squad_uuids": [SQUAD],
        "is_trial": False,
        "is_active": True,
        "is_visible": True,
        "sort_order": 0,
    }
    fields.update(overrides)
    return fields


async def test_visible_plans_are_sorted_and_filtered(db_session: AsyncSession) -> None:
    plans = PlanRepository(db_session)
    await plans.create(**_plan_fields("second", sort_order=2))
    await plans.create(**_plan_fields("first", sort_order=1))
    await plans.create(**_plan_fields("hidden", is_visible=False))
    await plans.create(**_plan_fields("archived", is_active=False))

    codes = [plan.code for plan in await plans.list_visible()]
    assert codes == ["first", "second"]


async def test_archive_keeps_row(db_session: AsyncSession) -> None:
    """Тариф не удаляется: на него ссылаются подписки и журнал."""
    plans = PlanRepository(db_session)
    plan = await plans.create(**_plan_fields("month"))
    await plans.archive(plan)

    assert await plans.get(plan.id) is not None
    assert await plans.list_visible() == []


async def test_active_trial_returns_only_trial(db_session: AsyncSession) -> None:
    plans = PlanRepository(db_session)
    await plans.create(**_plan_fields("month"))
    trial = await plans.create(**_plan_fields("trial", is_trial=True, duration_days=3))

    found = await plans.active_trial()
    assert found is not None
    assert found.id == trial.id


async def test_list_due_selects_only_expired_working_subscriptions(
    db_session: AsyncSession,
) -> None:
    plans = PlanRepository(db_session)
    plan = await plans.create(**_plan_fields("month"))
    subscriptions = SubscriptionRepository(db_session)
    now = datetime.now(UTC)

    for index, (state, delta) in enumerate(
        [
            (SubscriptionState.active, -1),
            (SubscriptionState.trial, -1),
            (SubscriptionState.active, 5),
            (SubscriptionState.expired, -10),
        ]
    ):
        user = User(email=f"due{index}@example.org", referral_code=f"due{index:05d}")
        db_session.add(user)
        await db_session.flush()
        await subscriptions.create(
            user_id=user.id,
            plan_id=plan.id,
            status=state,
            started_at=now - timedelta(days=30),
            expires_at=now + timedelta(days=delta),
            source=SubscriptionSource.purchase,
        )

    due = await subscriptions.list_due(now=now, limit=100)
    assert {row.status for row in due} == {SubscriptionState.active, SubscriptionState.trial}
    assert len(due) == 2


async def test_trial_grant_is_found_by_telegram_id(db_session: AsyncSession) -> None:
    trials = TrialRepository(db_session)
    assert await trials.get(777) is None
    await trials.create(telegram_id=777, user_id=None)
    assert await trials.get(777) is not None
