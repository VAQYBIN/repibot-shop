"""Схема подписок: ограничения, которые должна держать база."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Plan,
    Subscription,
    SubscriptionSource,
    TrafficResetStrategy,
    TrialGrant,
    User,
)
from repibot_core.domain.subscriptions import SubscriptionState

pytestmark = pytest.mark.docker


async def _plan(session: AsyncSession, *, code: str, is_trial: bool = False) -> Plan:
    plan = Plan(
        code=code,
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=is_trial,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _user(session: AsyncSession, *, code: str) -> User:
    user = User(email=f"{code}@example.org", referral_code=code)
    session.add(user)
    await session.flush()
    return user


async def test_user_has_numeric_panel_id(db_session: AsyncSession) -> None:
    """В панели 3.2.1 пользователь адресуется числом, а не uuid."""
    user = await _user(db_session, code="ref00001")
    user.remnawave_id = 4_294_967_296
    await db_session.flush()
    assert user.remnawave_id == 4_294_967_296


async def test_one_subscription_per_user(db_session: AsyncSession) -> None:
    """Вторая подписка того же пользователя не вставляется.

    `source` заполняется намеренно: без него первым сработал бы NOT NULL, и
    тест был бы зелёным даже без ограничения уникальности.
    """
    user = await _user(db_session, code="ref00002")
    plan = await _plan(db_session, code="month")
    now = datetime.now(UTC)

    for _ in range(2):
        db_session.add(
            Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionState.active,
                started_at=now,
                expires_at=now + timedelta(days=30),
                source=SubscriptionSource.purchase,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_only_one_active_trial_plan(db_session: AsyncSession) -> None:
    """Два активных триальных тарифа — неоднозначность, которую база не пропустит.

    Второй тариф добавляется прямо внутри `pytest.raises`: помощник `_plan`
    сам делает flush, и вынесенный за скобки flush уже ничего бы не поймал.
    """
    await _plan(db_session, code="trial-a", is_trial=True)
    with pytest.raises(IntegrityError):
        await _plan(db_session, code="trial-b", is_trial=True)


async def test_trial_grant_survives_user_deletion(db_session: AsyncSession) -> None:
    """Иначе триал накручивается удалением аккаунта и повторной регистрацией."""
    user = await _user(db_session, code="ref00003")
    db_session.add(TrialGrant(telegram_id=555, user_id=user.id))
    await db_session.flush()

    await db_session.delete(user)
    await db_session.flush()

    grant = await db_session.get(TrialGrant, 555)
    assert grant is not None
    assert grant.user_id is None
