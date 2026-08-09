"""Recurring YooKassa renewal attempts keep one stable cycle per expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    NotificationDelivery,
    PaymentAttempt,
    PaymentProvider,
    PaymentStatus,
    Subscription,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.payment_notifications import AutoRenewalService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


class FailingYooKassa:
    async def create_payment(self, **_: object) -> object:
        raise RuntimeError("provider is unavailable")


class RecordingYooKassa:
    def __init__(self) -> None:
        self.calls = 0

    async def create_payment(self, **_: object) -> object:
        self.calls += 1
        raise AssertionError("provider must not be called")


async def _subscription(session: AsyncSession) -> tuple[Subscription, datetime]:
    user = User(email="renew@example.org", telegram_id=100_002, referral_code="renew001")
    session.add(user)
    plan = await PlanRepository(session).create(
        code="renew",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("300.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    await session.flush()
    anchor = datetime.now(UTC) + timedelta(hours=24)
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=datetime.now(UTC),
        expires_at=anchor,
        auto_renew_enabled=True,
        source=SubscriptionSource.purchase,
        entitlement_price_rub=plan.price_rub,
        entitlement_duration_days=plan.duration_days,
    )
    session.add(subscription)
    order = await OrderRepository(session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key="saved-method",
        expires_at=anchor,
    )
    await PaymentAttemptRepository(session).get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key="saved-method-key",
        status=PaymentStatus.succeeded,
        verified_payload={"amount": "300.00", "currency": "RUB", "payment_method_id": "method-1"},
        verified_at=datetime.now(UTC),
    )
    await session.commit()
    return subscription, anchor


async def test_final_failed_attempt_disables_auto_renew_when_setting_enabled(
    db_session: AsyncSession,
) -> None:
    """Changing final-attempt handling or its unique cycle key must fail this test."""
    subscription, anchor = await _subscription(db_session)
    renewals = AutoRenewalService(db_session, FailingYooKassa(), get_settings())

    calls = []
    for offset in (-24, 6, 12):
        calls.append(await renewals.run(now=anchor + timedelta(hours=offset)))
    await db_session.refresh(subscription)

    attempts = list(
        (
            await db_session.scalars(
                select(PaymentAttempt).where(PaymentAttempt.provider == PaymentProvider.yookassa)
            )
        ).all()
    )
    failures = list(
        (
            await db_session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.kind.like("auto_renew_failed%")
                )
            )
        ).all()
    )
    assert calls == [1, 1, 1]
    assert subscription.auto_renew_enabled is False
    assert len(attempts) == 4  # one saved method + one deterministic attempt per configured offset
    assert len(failures) == 3


async def test_saved_method_absence_skips_auto_renewal(db_session: AsyncSession) -> None:
    """A missing method must prevent a provider request, not create a redirect payment."""
    _, anchor = await _subscription(db_session)
    saved = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.provider_key == "saved-method-key")
    )
    assert saved is not None
    saved.verified_payload = {"amount": "300.00", "currency": "RUB"}
    await db_session.commit()
    provider = RecordingYooKassa()

    attempted = await AutoRenewalService(db_session, provider, get_settings()).run(
        now=anchor - timedelta(hours=24)
    )

    assert attempted == 0
    assert provider.calls == 0


async def test_manual_renewal_makes_old_cycle_a_noop(db_session: AsyncSession) -> None:
    """Using an old expiry anchor after a manual renewal would charge the user twice."""
    subscription, anchor = await _subscription(db_session)
    subscription.expires_at = anchor + timedelta(days=30)
    await db_session.commit()
    provider = RecordingYooKassa()

    attempted = await AutoRenewalService(db_session, provider, get_settings()).run(
        now=anchor - timedelta(hours=24)
    )

    assert attempted == 0
    assert provider.calls == 0
