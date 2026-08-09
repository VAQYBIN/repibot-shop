"""Атомарная финализация проверенных платежей."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import (
    Order,
    OrderPurpose,
    OrderStatus,
    OutboxMessage,
    PaymentAttempt,
    PaymentProvider,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionEvent,
    SubscriptionEventType,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus
from repibot_core.services.payments import FinalizationResult, PaymentService
from repibot_core.services.promotions import PromotionInput, PromotionService
from repibot_core.services.provisioning import TOPIC_PROVISION

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _plan(session: AsyncSession, code: str, **overrides: object) -> Plan:
    fields: dict[str, object] = {
        "code": code,
        "name": {"ru": code, "en": code},
        "description": None,
        "duration_days": 30,
        "price_rub": Decimal("300.00"),
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
    return await PlanRepository(session).create(**fields)


async def _user(session: AsyncSession, code: str, *, referred_by_id: int | None = None) -> User:
    user = User(
        email=f"{code}@example.org",
        referral_code=code,
        referred_by_id=referred_by_id,
    )
    session.add(user)
    await session.flush()
    return user


async def _verified_attempt(
    session: AsyncSession,
    *,
    user: User,
    plan: Plan,
    key: str,
    purpose: OrderPurpose = OrderPurpose.purchase,
) -> int:
    order = await OrderRepository(session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key=f"order-{key}",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        purpose=purpose,
    )
    attempt = await PaymentAttemptRepository(session).get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key=f"payment-{key}",
        status=PaymentStatus.succeeded,
        verified_payload={"amount": str(order.amount_due_rub), "currency": "RUB"},
        verified_at=datetime.now(UTC),
    )
    await session.commit()
    return attempt.id


async def _finalize(factory: object, attempt_id: int) -> FinalizationResult:
    async with factory() as session:  # type: ignore[operator]
        result = await PaymentService(session).finalize_success(attempt_id)
        assert result is not None
        return result


async def _verified_bonus_promo_attempt(
    session: AsyncSession,
    *,
    user: User,
    plan: Plan,
    key: str,
    purpose: OrderPurpose = OrderPurpose.purchase,
) -> int:
    promos = PromotionService(session)
    promo = await promos.create(PromotionInput(code=f"BONUS-{key}", bonus_days=5))
    quote = await promos.prepare(user_id=user.id, code=promo.code, gross_rub=plan.price_rub)
    order = await OrderRepository(session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key=f"order-{key}",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        purpose=purpose,
        promo_code_id=promo.id,
    )
    await promos.reserve_prepared(order=order, user_id=user.id, quote=quote)
    # Админ меняет промокод уже после покупки: оплаченный bonus обязан остаться 5 днями.
    await promos.update(promo.id, PromotionInput(code=promo.code, bonus_days=20))
    attempt = await PaymentAttemptRepository(session).get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key=f"payment-{key}",
        status=PaymentStatus.succeeded,
        verified_payload={"amount": str(order.amount_due_rub), "currency": "RUB"},
        verified_at=datetime.now(UTC),
    )
    await session.commit()
    return attempt.id


async def test_two_finalizers_credit_days_and_outbox_once(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Удаление блокировки заказа вернуло бы двойное начисление при webhook retry."""
    plan = await _plan(db_session, "month")
    user = await _user(db_session, "pay00001")
    attempt_id = await _verified_attempt(db_session, user=user, plan=plan, key="race")
    factory = create_session_factory(engine)

    results = await asyncio.gather(_finalize(factory, attempt_id), _finalize(factory, attempt_id))

    assert sorted(result.already_finalized for result in results) == [False, True]
    events = await db_session.execute(
        select(func.count())
        .select_from(SubscriptionEvent)
        .where(SubscriptionEvent.origin_attempt_id == attempt_id)
    )
    assert events.scalar_one() == 1
    queued = await db_session.execute(
        select(func.count())
        .select_from(OutboxMessage)
        .where(OutboxMessage.topic == TOPIC_PROVISION)
    )
    assert queued.scalar_one() == 1


async def test_stars_success_can_be_recovered_after_recording_before_finalization(
    db_session: AsyncSession,
) -> None:
    """A crash after Telegram proof must leave a retryable, not permanently stuck, order."""
    plan = await _plan(db_session, "stars-retry")
    user = await _user(db_session, "stars001")
    created = await PaymentService(db_session).create_stars_order(
        user_id=user.id,
        plan_id=plan.id,
        purpose=OrderPurpose.purchase,
        client_key="stars-retry-order",
        promo_code=None,
    )
    assert created.invoice_payload is not None

    first = await PaymentService(db_session).confirm_stars_success(
        invoice_payload=created.invoice_payload, user_id=user.id, total_amount=199
    )
    recovered = await PaymentService(db_session).confirm_stars_success(
        invoice_payload=created.invoice_payload, user_id=user.id, total_amount=199
    )

    assert first is not None
    assert recovered == first
    result = await PaymentService(db_session).finalize_success(recovered)
    assert result is not None and result.already_finalized is False


async def test_late_yookassa_success_cannot_become_ttl_bypass_proof(
    db_session: AsyncSession,
) -> None:
    """Recording a late callback before the TTL gate would wrongly grant entitlement."""
    plan = await _plan(db_session, "yookassa-late-callback")
    user = await _user(db_session, "yooka001")
    order = await OrderRepository(db_session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key="yookassa-late-callback-order",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    attempt = await PaymentAttemptRepository(db_session).get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key="yookassa-late-callback-key",
        provider_payment_id="yookassa-late-callback-payment",
    )
    await db_session.commit()

    result = await PaymentService(db_session).finalize_success(
        verified_yookassa_payment=YooKassaPayment(
            id="yookassa-late-callback-payment",
            status=YooKassaPaymentStatus.succeeded,
            amount_rub=Decimal("300.00"),
            currency="RUB",
            confirmation_url=None,
        )
    )

    await db_session.refresh(order)
    await db_session.refresh(attempt)

    assert result == FinalizationResult(order_id=order.id, already_finalized=False, expired=True)
    assert order.status is OrderStatus.expired
    assert attempt.status is PaymentStatus.pending
    assert attempt.verified_payload is None
    assert attempt.verified_at is None


async def test_stars_payload_does_not_reveal_attempt_id(db_session: AsyncSession) -> None:
    plan = await _plan(db_session, "stars-opaque")
    user = await _user(db_session, "stars002")
    created = await PaymentService(db_session).create_stars_order(
        user_id=user.id,
        plan_id=plan.id,
        purpose=OrderPurpose.purchase,
        client_key="stars-opaque-order",
        promo_code=None,
    )
    attempt_id = await db_session.scalar(
        select(PaymentAttempt.id).where(PaymentAttempt.order_id == created.order.id)
    )

    assert created.invoice_payload is not None
    assert created.invoice_payload.split(".", maxsplit=1)[1] != str(attempt_id)


async def test_manual_same_plan_renewal_adds_purchased_days(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Если renewal не продлевает срок, повторная ручная оплата теряет купленные дни."""
    plan = await _plan(db_session, "month")
    user = await _user(db_session, "pay00002")
    first_attempt = await _verified_attempt(db_session, user=user, plan=plan, key="first")
    factory = create_session_factory(engine)
    await _finalize(factory, first_attempt)

    before = await db_session.scalar(select(Subscription).where(Subscription.user_id == user.id))
    assert before is not None
    expires_before = before.expires_at
    renew_attempt = await _verified_attempt(
        db_session, user=user, plan=plan, key="renew", purpose=OrderPurpose.renew
    )

    result = await _finalize(factory, renew_attempt)
    await db_session.refresh(before)

    assert result.already_finalized is False
    assert before.expires_at - expires_before == timedelta(days=30)


async def test_promo_bonus_is_snapshotted_and_applied_once_after_renewal(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Reading PromoCode at finalization would change paid bonus or grant it again on retry."""
    plan = await _plan(db_session, "bonus-renewal")
    user = await _user(db_session, "bonus0001")
    factory = create_session_factory(engine)
    first = await _verified_attempt(db_session, user=user, plan=plan, key="bonus-base")
    await _finalize(factory, first)
    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    assert subscription is not None
    expires_before = subscription.expires_at
    promoted = await _verified_bonus_promo_attempt(
        db_session, user=user, plan=plan, key="renewal", purpose=OrderPurpose.renew
    )

    await _finalize(factory, promoted)
    retry = await _finalize(factory, promoted)
    await db_session.refresh(subscription)
    bonuses = await db_session.scalar(
        select(func.count())
        .select_from(SubscriptionEvent)
        .where(
            SubscriptionEvent.user_id == user.id,
            SubscriptionEvent.type == SubscriptionEventType.bonus_days,
        )
    )

    assert retry.already_finalized is True
    assert subscription.expires_at - expires_before == timedelta(days=35)
    assert bonuses == 1


async def test_promo_bonus_follows_converted_purchase_on_plan_switch(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Applying bonus before switch conversion would leave it on the old plan's value."""
    old_plan = await _plan(db_session, "bonus-old", price_rub=Decimal("300.00"))
    new_plan = await _plan(db_session, "bonus-new", price_rub=Decimal("600.00"))
    user = await _user(db_session, "bonus0002")
    factory = create_session_factory(engine)
    first = await _verified_attempt(db_session, user=user, plan=old_plan, key="bonus-old")
    await _finalize(factory, first)
    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    assert subscription is not None
    subscription.expires_at = datetime.now(UTC) + timedelta(days=20, minutes=1)
    await db_session.commit()
    promoted = await _verified_bonus_promo_attempt(
        db_session, user=user, plan=new_plan, key="switch"
    )

    await _finalize(factory, promoted)
    await db_session.refresh(subscription)

    remaining = subscription.expires_at - datetime.now(UTC)
    assert timedelta(days=44) < remaining <= timedelta(days=45)


async def test_different_orders_for_new_user_finalize_without_subscription_race(
    db_session: AsyncSession, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Два первых заказа не должны падать на unique subscriptions.user_id."""
    plan = await _plan(db_session, "month")
    user = await _user(db_session, "pay00006")
    first_attempt = await _verified_attempt(db_session, user=user, plan=plan, key="first-race")
    second_attempt = await _verified_attempt(db_session, user=user, plan=plan, key="second-race")
    factory = create_session_factory(engine)
    barrier = asyncio.Barrier(2)
    original = SubscriptionRepository.get_for_user_for_update

    async def synchronized_absent_lookup(
        repository: SubscriptionRepository, user_id: int
    ) -> Subscription | None:
        subscription = await original(repository, user_id)
        if subscription is None:
            with suppress(TimeoutError):
                await asyncio.wait_for(barrier.wait(), timeout=0.1)
            # После исправления второй finalizer ждёт advisory lock и не
            # дойдёт до lookup, пока первый не создаст подписку.
        return subscription

    monkeypatch.setattr(
        SubscriptionRepository, "get_for_user_for_update", synchronized_absent_lookup
    )

    results = await asyncio.gather(
        _finalize(factory, first_attempt), _finalize(factory, second_attempt)
    )

    assert [result.already_finalized for result in results] == [False, False]
    fulfilled = await db_session.scalar(
        select(func.count())
        .select_from(Order)
        .where(Order.user_id == user.id, Order.status == OrderStatus.fulfilled)
    )
    assert fulfilled == 2
    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    assert subscription is not None
    remaining = subscription.expires_at - datetime.now(UTC)
    assert timedelta(days=59) < remaining <= timedelta(days=60)


async def test_paid_plan_switch_uses_saved_previous_entitlement_value(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Изменение цены старого тарифа не должно переписать уже купленный остаток."""
    old_plan = await _plan(db_session, "old", price_rub=Decimal("300.00"), duration_days=30)
    new_plan = await _plan(db_session, "new", price_rub=Decimal("600.00"), duration_days=30)
    user = await _user(db_session, "pay00003")
    factory = create_session_factory(engine)
    first_attempt = await _verified_attempt(db_session, user=user, plan=old_plan, key="old")
    await _finalize(factory, first_attempt)
    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    assert subscription is not None
    subscription.expires_at = datetime.now(UTC) + timedelta(days=20, minutes=1)
    old_plan.price_rub = Decimal("1200.00")
    await db_session.commit()

    switch_attempt = await _verified_attempt(db_session, user=user, plan=new_plan, key="switch")
    await _finalize(factory, switch_attempt)
    await db_session.refresh(subscription)

    remaining = subscription.expires_at - datetime.now(UTC)
    # 20 дней старого тарифа по 10 ₽/день = 10 дней нового по 20 ₽/день,
    # после чего добавляются 30 оплаченных дней. Цена, поднятая до 1200 ₽,
    # дала бы около 70 дней и нарушила бы это условие.
    assert timedelta(days=39) < remaining <= timedelta(days=40)


async def test_referral_bonus_is_added_after_purchased_duration(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Перестановка начислений не должна подменить базу для referral bonus."""
    plan = await _plan(db_session, "month")
    referrer = await _user(db_session, "pay00004")
    referee = await _user(db_session, "pay00005", referred_by_id=referrer.id)
    factory = create_session_factory(engine)
    attempt_id = await _verified_attempt(db_session, user=referee, plan=plan, key="reward")

    await _finalize(factory, attempt_id)

    reward = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == referrer.id)
    )
    assert reward is not None
    remaining = reward.expires_at - datetime.now(UTC)
    # 10% от оплаченных 30 дней, то есть ровно три бонусных дня.
    assert timedelta(days=2) < remaining <= timedelta(days=3)
    provisioning = await db_session.scalar(
        select(func.count())
        .select_from(OutboxMessage)
        .where(OutboxMessage.topic == TOPIC_PROVISION)
    )
    assert provisioning == 1
