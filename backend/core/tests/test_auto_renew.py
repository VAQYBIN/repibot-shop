"""Автопродление YooKassa держит ровно один цикл на дату окончания."""

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
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus
from repibot_core.services.payment_methods import PaymentMethodService
from repibot_core.services.payment_notifications import AutoRenewalService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


class FailingYooKassa:
    def __init__(self) -> None:
        self._number = 0

    async def create_payment(
        self,
        *,
        idempotence_key: str,
        amount_rub: Decimal,
        return_url: str,
        description: str,
        save_payment_method: bool,
        payment_method_id: str | None = None,
    ) -> YooKassaPayment:
        _ = (
            idempotence_key,
            amount_rub,
            return_url,
            description,
            save_payment_method,
            payment_method_id,
        )
        self._number += 1
        return _payment(f"failed-{self._number}", YooKassaPaymentStatus.canceled)

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        raise AssertionError(f"provider must not fetch {payment_id}")


class RecordingYooKassa:
    def __init__(self) -> None:
        self.calls = 0

    async def create_payment(
        self,
        *,
        idempotence_key: str,
        amount_rub: Decimal,
        return_url: str,
        description: str,
        save_payment_method: bool,
        payment_method_id: str | None = None,
    ) -> YooKassaPayment:
        _ = (
            idempotence_key,
            amount_rub,
            return_url,
            description,
            save_payment_method,
            payment_method_id,
        )
        self.calls += 1
        raise AssertionError("provider must not be called")

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        raise AssertionError(f"provider must not fetch {payment_id}")


class ScriptedYooKassa:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.keys: list[str] = []
        self.payments: dict[str, YooKassaPayment] = {}

    async def create_payment(
        self,
        *,
        idempotence_key: str,
        amount_rub: Decimal,
        return_url: str,
        description: str,
        save_payment_method: bool,
        payment_method_id: str | None = None,
    ) -> YooKassaPayment:
        _ = amount_rub, return_url, description, save_payment_method, payment_method_id
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
    await session.flush()
    # Карта живёт своей строкой, а не выводится из payload прошлой оплаты:
    # payment_method.id приходит и у платежей без сохранения.
    await PaymentMethodService(session).save(
        user.id, provider_method_id="method-1", title="Bank card *4444"
    )
    await session.commit()
    return subscription, anchor


async def test_final_failed_attempt_disables_auto_renew_when_setting_enabled(
    db_session: AsyncSession,
) -> None:
    """Правка последней попытки или ключа цикла обязана уронить этот тест."""
    subscription, anchor = await _subscription(db_session)
    renewals = AutoRenewalService(db_session, FailingYooKassa(), get_settings())

    calls = []
    # Вторая и третья попытки идут через 6 и 12 часов после предыдущей,
    # то есть за 18 и за 6 часов до срока.
    for offset in (-24, -18, -6):
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
    assert len(attempts) == 3  # по одной попытке на каждое настроенное смещение
    assert len(failures) == 3


async def test_saved_method_absence_skips_auto_renewal(db_session: AsyncSession) -> None:
    """Без сохранённой карты запроса к провайдеру быть не должно вовсе."""
    subscription, anchor = await _subscription(db_session)
    await PaymentMethodService(db_session).revoke(subscription.user_id)
    # Отвязка гасит и автопродление, но проверяем именно отсутствие карты.
    subscription.auto_renew_enabled = True
    await db_session.commit()
    provider = RecordingYooKassa()

    attempted = await AutoRenewalService(db_session, provider, get_settings()).run(
        now=anchor - timedelta(hours=24)
    )

    assert attempted == 0
    assert provider.calls == 0


async def test_manual_renewal_makes_old_cycle_a_noop(db_session: AsyncSession) -> None:
    """Старая дата окончания после ручного продления списала бы деньги дважды."""
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
    """Таймаут после начала запроса добирается тем же ключом идемпотентности."""
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
    """Списание по устаревшему циклу нельзя молча выбросить."""
    subscription, anchor = await _subscription(db_session)

    class ManualDuringRequest(ScriptedYooKassa):
        async def create_payment(
            self,
            *,
            idempotence_key: str,
            amount_rub: Decimal,
            return_url: str,
            description: str,
            save_payment_method: bool,
            payment_method_id: str | None = None,
        ) -> YooKassaPayment:
            subscription.expires_at = anchor + timedelta(days=30)
            await db_session.commit()
            return await super().create_payment(
                idempotence_key=idempotence_key,
                amount_rub=amount_rub,
                return_url=return_url,
                description=description,
                save_payment_method=save_payment_method,
                payment_method_id=payment_method_id,
            )

    provider = ManualDuringRequest([_payment("late-success", YooKassaPaymentStatus.succeeded)])
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
    """Отказ старого запроса — не повод выключать автопродление после ручной оплаты."""
    subscription, anchor = await _subscription(db_session)

    class ManualDuringRequest(ScriptedYooKassa):
        async def create_payment(
            self,
            *,
            idempotence_key: str,
            amount_rub: Decimal,
            return_url: str,
            description: str,
            save_payment_method: bool,
            payment_method_id: str | None = None,
        ) -> YooKassaPayment:
            subscription.expires_at = anchor + timedelta(days=30)
            await db_session.commit()
            return await super().create_payment(
                idempotence_key=idempotence_key,
                amount_rub=amount_rub,
                return_url=return_url,
                description=description,
                save_payment_method=save_payment_method,
                payment_method_id=payment_method_id,
            )

    provider = ManualDuringRequest([_payment("late-cancel", YooKassaPaymentStatus.canceled)])
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
    """Падение после записи успеха не должно бросить оплаченное продление."""
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

    order = await db_session.scalar(select(Order).where(Order.client_key.like("auto-renew:%")))
    assert order is not None and order.status is OrderStatus.fulfilled


async def test_fresh_run_fulfills_recorded_success_after_local_ttl_expired(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Подтверждённый ответ YooKassa важнее истёкшего местного заказа."""
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
    # Срок заказа неизменяем; к моменту прогона ниже он и так позади, поэтому
    # истечение достаточно отразить статусом.
    order.status = OrderStatus.expired
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
    """Истечение подписки не отменяет поздние попытки и их уведомления."""
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
