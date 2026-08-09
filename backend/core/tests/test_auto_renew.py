"""Recurring YooKassa renewal attempts keep one stable cycle per expiry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    NotificationDelivery,
    Order,
    OrderStatus,
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
from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus
from repibot_core.services.payment_notifications import AutoRenewalService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


class FailingYooKassa:
    def __init__(self) -> None:
        self._number = 0

    async def create_payment(self, **_: object) -> YooKassaPayment:
        self._number += 1
        return _payment(f"failed-{self._number}", YooKassaPaymentStatus.canceled)


class RecordingYooKassa:
    def __init__(self) -> None:
        self.calls = 0

    async def create_payment(self, **_: object) -> object:
        self.calls += 1
        raise AssertionError("provider must not be called")


class ScriptedYooKassa:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.keys: list[str] = []
        self.payments: dict[str, YooKassaPayment] = {}

    async def create_payment(self, *, idempotence_key: str, **_: object) -> YooKassaPayment:
        self.keys.append(idempotence_key)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, YooKassaPayment)
        self.payments[outcome.id] = outcome
        return outcome

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        return self.payments[payment_id]


def _payment(payment_id: str, status: YooKassaPaymentStatus) -> YooKassaPayment:
    return YooKassaPayment(
        id=payment_id,
        status=status,
        amount_rub=Decimal("300.00"),
        currency="RUB",
        confirmation_url=None,
        payment_method_id="method-1",
    )


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


async def test_timeout_replays_same_durable_cycle_without_creating_second_charge(
    db_session: AsyncSession,
) -> None:
    """Timeout after request start must be recovered with the original idempotence key."""
    _, anchor = await _subscription(db_session)
    provider = ScriptedYooKassa(
        [TimeoutError("lost response"), _payment("recovered", YooKassaPaymentStatus.succeeded)]
    )
    service = AutoRenewalService(db_session, provider, get_settings())

    await service.run(now=anchor - timedelta(hours=24))
    await service.run(now=anchor - timedelta(hours=23))

    renewals = list(
        (await db_session.scalars(select(Order).where(Order.client_key.like("auto-renew:%")))).all()
    )
    assert len(renewals) == 1
    assert renewals[0].status is OrderStatus.fulfilled
    assert len(provider.keys) == 2
    assert provider.keys[0] == provider.keys[1]


async def test_success_after_manual_renewal_is_recorded_and_fulfilled(
    db_session: AsyncSession,
) -> None:
    """A charged stale response must never be silently dropped."""
    subscription, anchor = await _subscription(db_session)

    class ManualDuringRequest(ScriptedYooKassa):
        async def create_payment(self, **kwargs: object) -> YooKassaPayment:
            subscription.expires_at = anchor + timedelta(days=30)
            await db_session.commit()
            return await super().create_payment(**kwargs)

    provider = ManualDuringRequest(
        [_payment("late-success", YooKassaPaymentStatus.succeeded)]
    )
    await AutoRenewalService(db_session, provider, get_settings()).run(
        now=anchor - timedelta(hours=24)
    )

    attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.provider_payment_id == "late-success")
    )
    assert attempt is not None and attempt.status is PaymentStatus.succeeded
    assert (
        await db_session.scalar(select(Order.status).where(Order.id == attempt.order_id))
        is OrderStatus.fulfilled
    )


async def test_stale_confirmed_failure_does_not_disable_or_notify_new_cycle(
    db_session: AsyncSession,
) -> None:
    """A declined old request is not a reason to turn off auto-renew after manual renewal."""
    subscription, anchor = await _subscription(db_session)

    class ManualDuringRequest(ScriptedYooKassa):
        async def create_payment(self, **kwargs: object) -> YooKassaPayment:
            subscription.expires_at = anchor + timedelta(days=30)
            await db_session.commit()
            return await super().create_payment(**kwargs)

    provider = ManualDuringRequest(
        [_payment("late-cancel", YooKassaPaymentStatus.canceled)]
    )
    await AutoRenewalService(db_session, provider, get_settings()).run(
        now=anchor - timedelta(hours=24)
    )
    await db_session.refresh(subscription)

    failures = await db_session.scalar(
        select(NotificationDelivery.id).where(NotificationDelivery.kind.like("auto_renew_failed%"))
    )
    assert subscription.auto_renew_enabled is True
    assert failures is None


async def test_fresh_run_finalizes_recorded_success_after_crash_before_finalizer(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after persisting provider success must not strand a charged renewal."""
    subscription, anchor = await _subscription(db_session)
    provider = ScriptedYooKassa([_payment("crash-success", YooKassaPaymentStatus.succeeded)])
    interrupted = AutoRenewalService(db_session, provider, get_settings())

    async def crash(_: int) -> None:
        raise RuntimeError("worker crashed after durable provider record")

    monkeypatch.setattr(interrupted, "_finalize", crash)
    with pytest.raises(RuntimeError, match="worker crashed"):
        await interrupted.run(now=anchor - timedelta(hours=24))

    subscription.expires_at = anchor + timedelta(days=30)
    await db_session.commit()

    recovered = AutoRenewalService(db_session, RecordingYooKassa(), get_settings())
    await recovered.run(now=anchor - timedelta(hours=1))

    order = await db_session.scalar(
        select(Order).where(Order.client_key.like("auto-renew:%"))
    )
    assert order is not None and order.status is OrderStatus.fulfilled


async def test_fresh_run_fulfills_recorded_success_after_local_ttl_expired(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirmed YooKassa truth must win over an expired local renewal order."""
    subscription, anchor = await _subscription(db_session)
    provider = ScriptedYooKassa([_payment("ttl-success", YooKassaPaymentStatus.succeeded)])
    interrupted = AutoRenewalService(db_session, provider, get_settings())

    async def crash(_: int) -> None:
        raise RuntimeError("worker crashed after durable provider record")

    monkeypatch.setattr(interrupted, "_finalize", crash)
    with pytest.raises(RuntimeError, match="worker crashed"):
        await interrupted.run(now=anchor - timedelta(hours=24))

    order = await db_session.scalar(select(Order).where(Order.client_key.like("auto-renew:%")))
    assert order is not None
    order.status = OrderStatus.expired
    order.expires_at = anchor - timedelta(days=8)
    subscription.expires_at = anchor + timedelta(days=30)
    await db_session.commit()

    await AutoRenewalService(db_session, RecordingYooKassa(), get_settings()).run(
        now=anchor + timedelta(days=8)
    )
    await db_session.refresh(order)

    assert order.status is OrderStatus.fulfilled


async def test_expired_subscription_runs_second_retry_and_overdue_run_catches_up_in_order(
    db_session: AsyncSession,
) -> None:
    """Expiry cron must not suppress +6/+12 retries or collapse missed failure events."""
    subscription, anchor = await _subscription(db_session)
    provider = ScriptedYooKassa(
        [
            _payment("failed-1", YooKassaPaymentStatus.canceled),
            _payment("failed-2", YooKassaPaymentStatus.canceled),
            _payment("failed-3", YooKassaPaymentStatus.canceled),
        ]
    )
    service = AutoRenewalService(db_session, provider, get_settings())

    await service.run(now=anchor - timedelta(hours=24))
    subscription.status = SubscriptionState.expired
    await db_session.commit()
    await service.run(now=anchor + timedelta(hours=12))

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
    renewal_numbers = [
        attempt.attempt_no for attempt in attempts if attempt.provider_key != "saved-method-key"
    ]
    assert renewal_numbers == [1, 2, 3]
    assert len(failures) == 3
