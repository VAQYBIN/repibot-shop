"""Заказы и попытки оплаты получают коммерческие снимки и ключи идемпотентности."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import (
    OrderPurpose,
    PaymentProvider,
    Plan,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository

pytestmark = pytest.mark.docker


async def _plan(session: AsyncSession) -> Plan:
    plan = Plan(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
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
    session.add(plan)
    await session.flush()
    return plan


async def _user(session: AsyncSession, *, code: str = "order001") -> User:
    user = User(email=f"{code}@example.org", referral_code=code)
    session.add(user)
    await session.flush()
    return user


async def test_pending_order_snapshots_plan_and_attempt_is_reused(db_session: AsyncSession) -> None:
    """Изменение тарифа после старта оплаты не меняет уже выставленный счёт."""
    plan = await _plan(db_session)
    user = await _user(db_session)
    orders = OrderRepository(db_session)
    attempts = PaymentAttemptRepository(db_session)

    order = await orders.create_pending(
        user_id=user.id,
        plan=plan,
        client_key="order-client-key-1",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    plan.name = {"ru": "Новый месяц", "en": "New month"}
    plan.price_rub = Decimal("399.00")
    first = await attempts.get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key="provider-key-1",
    )
    retry = await attempts.get_or_create(
        order_id=order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key="provider-key-1",
    )

    assert order.plan_code_snapshot == "month"
    assert order.plan_name_snapshot == {"ru": "Месяц", "en": "Month"}
    assert order.duration_days_snapshot == 30
    assert order.gross_rub == Decimal("299.00")
    assert order.amount_due_rub == Decimal("299.00")
    assert first.id == retry.id


async def test_duplicate_client_key_for_user_is_rejected(db_session: AsyncSession) -> None:
    """Повторный запрос клиента не должен создать два заказа для одной покупки."""
    plan = await _plan(db_session)
    user = await _user(db_session)
    orders = OrderRepository(db_session)
    expires_at = datetime.now(UTC) + timedelta(minutes=30)

    await orders.create_pending(
        user_id=user.id, plan=plan, client_key="same-client-key", expires_at=expires_at
    )
    with pytest.raises(IntegrityError):
        await orders.create_pending(
            user_id=user.id, plan=plan, client_key="same-client-key", expires_at=expires_at
        )


async def test_duplicate_provider_payment_id_is_rejected(db_session: AsyncSession) -> None:
    """Один платёж провайдера нельзя связать с двумя попытками оплаты."""
    plan = await _plan(db_session)
    user = await _user(db_session)
    orders = OrderRepository(db_session)
    attempts = PaymentAttemptRepository(db_session)
    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    first_order = await orders.create_pending(
        user_id=user.id, plan=plan, client_key="first-order-key", expires_at=expires_at
    )
    second_order = await orders.create_pending(
        user_id=user.id, plan=plan, client_key="second-order-key", expires_at=expires_at
    )
    first = await attempts.get_or_create(
        order_id=first_order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key="first-provider-key",
    )
    first.provider_payment_id = "provider-payment-1"
    await db_session.flush()

    duplicate = await attempts.get_or_create(
        order_id=second_order.id,
        provider=PaymentProvider.yookassa,
        attempt_no=1,
        provider_key="second-provider-key",
    )
    duplicate.provider_payment_id = "provider-payment-1"
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_concurrent_retry_returns_one_existing_provider_attempt(
    db_session: AsyncSession, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Гонка двух одинаковых retry не должна отдавать одному клиенту IntegrityError."""
    plan = await _plan(db_session)
    user = await _user(db_session)
    order = await OrderRepository(db_session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key="concurrent-order-key",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await db_session.commit()

    barrier = asyncio.Barrier(2)
    lock = asyncio.Lock()
    gated_queries = 0
    original_execute = AsyncSession.execute

    async def gate_initial_lookup(
        session: AsyncSession, statement: Any, *args: Any, **kwargs: Any
    ) -> Any:
        nonlocal gated_queries
        should_wait = False
        if "INSERT INTO payment_attempts" in str(statement):
            async with lock:
                if gated_queries < 2:
                    gated_queries += 1
                    should_wait = True
        if should_wait:
            await barrier.wait()
        return await original_execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", gate_initial_lookup)
    factory = create_session_factory(engine)

    async def retry() -> int:
        async with factory() as session:
            attempt = await PaymentAttemptRepository(session).get_or_create(
                order_id=order.id,
                provider=PaymentProvider.yookassa,
                attempt_no=1,
                provider_key="concurrent-provider-key",
            )
            await session.commit()
            return attempt.id

    first_id, second_id = await asyncio.gather(retry(), retry())

    assert first_id == second_id


async def test_order_snapshot_fields_cannot_be_mutated(db_session: AsyncSession) -> None:
    """Изменение снимка цены после создания заказа не должно пройти серверный trigger."""
    plan = await _plan(db_session)
    user = await _user(db_session)
    order = await OrderRepository(db_session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key="immutable-order-key",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )

    order.price_rub_snapshot = Decimal("1.00")
    with pytest.raises(DBAPIError, match="order commercial snapshot is immutable"):
        await db_session.flush()


@pytest.mark.parametrize("field", ("user_id", "purpose", "client_key", "expires_at"))
async def test_order_intent_fields_cannot_be_mutated(db_session: AsyncSession, field: str) -> None:
    """Неизменяемое коммерческое решение включает владельца, назначение, ключ и срок."""
    plan = await _plan(db_session)
    user = await _user(db_session)
    order = await OrderRepository(db_session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key=f"immutable-intent-{field}",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )

    if field == "user_id":
        other = await _user(db_session, code="order002")
        order.user_id = other.id
    elif field == "purpose":
        order.purpose = OrderPurpose.gift
    elif field == "client_key":
        order.client_key = "different-idempotency-key"
    else:
        order.expires_at += timedelta(minutes=10)

    with pytest.raises(DBAPIError, match="order commercial snapshot is immutable"):
        await db_session.flush()


async def test_order_cannot_point_at_a_promo_code_that_does_not_exist(
    db_session: AsyncSession,
) -> None:
    """Скидка со ссылкой в никуда превращает разбор денег в догадки.

    Промокоды не удаляются, а снимаются с продажи, поэтому расхождение может
    появиться только из ошибки в коде — и должно останавливаться базой, а не
    обнаруживаться через месяц в отчёте.
    """
    plan = await _plan(db_session)
    user = await _user(db_session, code="orderfk1")

    with pytest.raises(IntegrityError):
        await OrderRepository(db_session).create_pending(
            user_id=user.id,
            plan=plan,
            client_key="order-with-unknown-promo",
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
            purpose=OrderPurpose.purchase,
            gross_rub=plan.price_rub,
            discount_rub=Decimal("10.00"),
            promo_code_id=10_000_000,
        )
