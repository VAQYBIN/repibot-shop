"""Реферальная награда — дни с неизменяемым источником в оплаченном заказе."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    OrderPurpose,
    PaymentProvider,
    PaymentStatus,
    Plan,
    ReferralReward,
    SubscriptionEvent,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.services.payments import PaymentService
from repibot_core.services.referrals import ReferralService
from repibot_core.settings import Settings

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _plan(session: AsyncSession, code: str, *, days: int = 30) -> Plan:
    return await PlanRepository(session).create(
        code=code,
        name={"ru": code, "en": code},
        description=None,
        duration_days=days,
        price_rub=Decimal("300.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )


async def _user(session: AsyncSession, code: str, *, referrer: User | None = None) -> User:
    user = User(
        email=f"{code}@example.org",
        referral_code=code,
        referred_by_id=None if referrer is None else referrer.id,
    )
    session.add(user)
    await session.flush()
    return user


async def _paid_attempt(
    session: AsyncSession, *, user: User, plan: Plan, key: str, gift: bool = False
) -> int:
    order = await OrderRepository(session).create_pending(
        user_id=user.id,
        plan=plan,
        purpose=OrderPurpose.gift if gift else OrderPurpose.purchase,
        client_key=f"order-{key}",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    attempt = await PaymentAttemptRepository(session).get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key=f"attempt-{key}",
        status=PaymentStatus.succeeded,
        verified_payload={"amount": str(order.amount_due_rub), "currency": "RUB"},
        verified_at=datetime.now(UTC),
    )
    await session.commit()
    return attempt.id


async def test_first_mode_rewards_only_first_successful_referee_order(
    db_session: AsyncSession,
) -> None:
    """Вторая оплата приглашённого не создаёт второй источник в режиме first."""
    plan = await _plan(db_session, "first-plan")
    referrer = await _user(db_session, "first-referrer")
    referee = await _user(db_session, "first-referee", referrer=referrer)
    first = await _paid_attempt(db_session, user=referee, plan=plan, key="first-one")
    second = await _paid_attempt(db_session, user=referee, plan=plan, key="first-two")
    settings = Settings(referral_reward_percent=10, referral_reward_mode="first")

    await PaymentService(db_session, settings).finalize_success(first)
    await PaymentService(db_session, settings).finalize_success(second)

    rewards = list((await db_session.scalars(select(ReferralReward))).all())
    assert [(reward.origin_order_id, reward.days) for reward in rewards] == [(1, 3)]


async def test_every_mode_uses_immutable_order_duration_and_minimum_one_day(
    db_session: AsyncSession,
) -> None:
    plan = await _plan(db_session, "every-plan", days=1)
    referrer = await _user(db_session, "every-referrer")
    referee = await _user(db_session, "every-referee", referrer=referrer)
    first = await _paid_attempt(db_session, user=referee, plan=plan, key="every-one")
    second = await _paid_attempt(db_session, user=referee, plan=plan, key="every-two")
    settings = Settings(referral_reward_percent=1, referral_reward_mode="every")

    await PaymentService(db_session, settings).finalize_success(first)
    plan.duration_days = 365
    await db_session.commit()
    await PaymentService(db_session, settings).finalize_success(second)

    assert await db_session.scalar(select(func.count()).select_from(ReferralReward)) == 2
    assert list((await db_session.scalars(select(ReferralReward.days))).all()) == [1, 1]


async def test_gift_order_never_creates_referral_reward(db_session: AsyncSession) -> None:
    plan = await _plan(db_session, "gift-plan")
    referrer = await _user(db_session, "gift-referrer")
    referee = await _user(db_session, "gift-referee", referrer=referrer)
    attempt = await _paid_attempt(db_session, user=referee, plan=plan, key="gift", gift=True)

    await PaymentService(db_session).finalize_success(attempt)

    assert await db_session.scalar(select(func.count()).select_from(ReferralReward)) == 0
    assert await db_session.scalar(select(func.count()).select_from(SubscriptionEvent)) == 0


async def test_referral_service_has_order_credit_entrypoint(db_session: AsyncSession) -> None:
    """Финализатор отдаёт правило отдельному реферальному сервису."""
    service = ReferralService(db_session, Settings())

    assert await service.credit_for_order(999_999) is None
