"""YooKassa callbacks are hints: provider data remains the source of truth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import (
    Order,
    OrderStatus,
    PaymentAttempt,
    PaymentProvider,
    PaymentStatus,
    Plan,
    PromoCode,
    PromoReservation,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository
from repibot_core.integrations.yookassa.testing import FakeYooKassa

pytestmark = pytest.mark.docker


async def _pending_attempt(engine: AsyncEngine, *, expired: bool = False) -> tuple[int, int, str]:
    async with create_session_factory(engine)() as session:
        plan = Plan(
            code="yookassa-month",
            name={"ru": "Месяц", "en": "Month"},
            description=None,
            duration_days=30,
            price_rub=Decimal("254.15"),
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
        user = User(email="yookassa@example.org", referral_code="yookassa01")
        session.add_all((plan, user))
        await session.flush()
        order = await OrderRepository(session).create_pending(
            user_id=user.id,
            plan=plan,
            client_key="yookassa-order",
            expires_at=(
                datetime.now(UTC) - timedelta(minutes=1)
                if expired
                else datetime.now(UTC) + timedelta(minutes=30)
            ),
        )
        attempt = await PaymentAttemptRepository(session).get_or_create(
            order_id=order.id,
            provider=PaymentProvider.yookassa,
            attempt_no=1,
            provider_key="yookassa-attempt",
            provider_payment_id="payment-1",
        )
        if expired:
            promo = PromoCode(code="expired-order")
            session.add(promo)
            await session.flush()
            session.add(
                PromoReservation(
                    order_id=order.id,
                    promo_code_id=promo.id,
                    user_id=user.id,
                    expires_at=datetime.now(UTC) + timedelta(minutes=30),
                )
            )
        await session.commit()
        return order.id, attempt.id, "payment-1"


async def _order_status(engine: AsyncEngine, order_id: int) -> OrderStatus:
    async with create_session_factory(engine)() as session:
        return await session.scalar(select(Order.status).where(Order.id == order_id))  # type: ignore[return-value]


async def _attempt(engine: AsyncEngine, attempt_id: int) -> PaymentAttempt:
    async with create_session_factory(engine)() as session:
        attempt = await session.get(PaymentAttempt, attempt_id)
        assert attempt is not None
        return attempt


async def _promo_reservation_count(engine: AsyncEngine, order_id: int) -> int:
    async with create_session_factory(engine)() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(PromoReservation)
                .where(PromoReservation.order_id == order_id)
            )
        )


async def test_webhook_fetches_provider_truth_before_finalizing(
    api_client: AsyncClient, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trusting webhook amount/status would let a forged callback grant access."""
    from repibot_api.routers import webhooks

    fake = FakeYooKassa()
    order_id, _attempt_id, payment_id = await _pending_attempt(engine)
    fake.set_payment(payment_id, status="succeeded", amount="254.15", currency="RUB")
    monkeypatch.setattr(webhooks, "create_yookassa_client", lambda: fake)

    response = await api_client.post(
        "/webhook/yookassa",
        json={"object": {"id": payment_id, "status": "canceled", "amount": {"value": "1.00"}}},
    )

    assert response.status_code == 204
    assert await _order_status(engine, order_id) is OrderStatus.fulfilled


@pytest.mark.parametrize(("amount", "currency"), [("1.00", "RUB"), ("254.15", "USD")])
async def test_webhook_rejects_provider_amount_or_currency_mismatch(
    api_client: AsyncClient,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    amount: str,
    currency: str,
) -> None:
    """A success status alone cannot settle an order with a different commercial snapshot."""
    from repibot_api.routers import webhooks

    fake = FakeYooKassa()
    order_id, _attempt_id, payment_id = await _pending_attempt(engine)
    fake.set_payment(payment_id, status="succeeded", amount=amount, currency=currency)
    monkeypatch.setattr(webhooks, "create_yookassa_client", lambda: fake)

    response = await api_client.post("/webhook/yookassa", json={"object": {"id": payment_id}})

    assert response.status_code == 204
    assert await _order_status(engine, order_id) is OrderStatus.pending


async def test_duplicate_webhook_is_deduplicated_by_verified_provider_state(
    api_client: AsyncClient, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider retry must not create a second finalization side effect."""
    from repibot_api.routers import webhooks

    fake = FakeYooKassa()
    order_id, attempt_id, payment_id = await _pending_attempt(engine)
    fake.set_payment(payment_id, status="succeeded", amount="254.15", currency="RUB")
    monkeypatch.setattr(webhooks, "create_yookassa_client", lambda: fake)

    first = await api_client.post("/webhook/yookassa", json={"object": {"id": payment_id}})
    second = await api_client.post("/webhook/yookassa", json={"object": {"id": payment_id}})
    attempt = await _attempt(engine, attempt_id)

    assert (first.status_code, second.status_code) == (204, 204)
    assert await _order_status(engine, order_id) is OrderStatus.fulfilled
    assert attempt.status.value == "succeeded"
    assert attempt.verified_payload == {
        "amount": "254.15",
        "currency": "RUB",
        "payment_method_id": None,
        "status": "succeeded",
    }


async def test_expired_order_is_marked_expired_and_never_fulfilled(
    api_client: AsyncClient, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider success after the 30-minute window must not resurrect the commercial order."""
    from repibot_api.routers import webhooks

    fake = FakeYooKassa()
    order_id, _attempt_id, payment_id = await _pending_attempt(engine, expired=True)
    fake.set_payment(payment_id, status="succeeded", amount="254.15", currency="RUB")
    monkeypatch.setattr(webhooks, "create_yookassa_client", lambda: fake)

    response = await api_client.post("/webhook/yookassa", json={"object": {"id": payment_id}})

    assert response.status_code == 204
    assert await _order_status(engine, order_id) is OrderStatus.expired
    assert await _promo_reservation_count(engine, order_id) == 0


async def test_retry_recovers_after_local_finalizer_crash_without_stranding_attempt(
    api_client: AsyncClient, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crash after provider GET must roll back verification with the unfinished order."""
    from repibot_api.routers import webhooks
    from repibot_core.services.payments import PaymentService

    fake = FakeYooKassa()
    order_id, attempt_id, payment_id = await _pending_attempt(engine)
    fake.set_payment(payment_id, status="succeeded", amount="254.15", currency="RUB")
    monkeypatch.setattr(webhooks, "create_yookassa_client", lambda: fake)
    original = PaymentService._stage_referral_bonus

    async def crash_after_verification(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated cancellation after verification")

    monkeypatch.setattr(PaymentService, "_stage_referral_bonus", crash_after_verification)
    with pytest.raises(RuntimeError, match="simulated cancellation"):
        await api_client.post("/webhook/yookassa", json={"object": {"id": payment_id}})
    attempt_after_crash = await _attempt(engine, attempt_id)

    assert await _order_status(engine, order_id) is OrderStatus.pending
    assert attempt_after_crash.status is PaymentStatus.pending
    assert attempt_after_crash.verified_payload is None

    monkeypatch.setattr(PaymentService, "_stage_referral_bonus", original)
    recovered = await api_client.post("/webhook/yookassa", json={"object": {"id": payment_id}})

    assert recovered.status_code == 204
    assert await _order_status(engine, order_id) is OrderStatus.fulfilled
