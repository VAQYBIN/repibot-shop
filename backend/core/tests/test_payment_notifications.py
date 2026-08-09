"""Durable fan-out of payment events to every linked channel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    NotificationDelivery,
    Order,
    OutboxMessage,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.services.outbox import MAX_ATTEMPTS, OutboxDispatcher
from repibot_core.services.payment_notifications import NotificationService

pytestmark = pytest.mark.docker


async def _order(session: AsyncSession, *, telegram: bool, verified_email: bool) -> Order:
    user = User(
        email="notice@example.org" if verified_email else None,
        email_verified_at=datetime.now(UTC) if verified_email else None,
        telegram_id=100_001 if telegram else None,
        referral_code="notice01",
    )
    session.add(user)
    plan = await PlanRepository(session).create(
        code="notice",
        name={"ru": "Уведомления", "en": "Notifications"},
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
    return await OrderRepository(session).create_pending(
        user_id=user.id,
        plan=plan,
        client_key="notice-order",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )


async def test_success_enqueues_each_available_channel_once(db_session: AsyncSession) -> None:
    """Removing either recipient or the delivery uniqueness must fail this test."""
    order = await _order(db_session, telegram=True, verified_email=True)
    notifications = NotificationService(db_session)

    await notifications.enqueue_payment_event(order.id, "payment_succeeded")
    await notifications.enqueue_payment_event(order.id, "payment_succeeded")
    await db_session.commit()

    topics = list(
        (await db_session.scalars(select(OutboxMessage.topic).order_by(OutboxMessage.topic))).all()
    )
    deliveries = list(
        (
            await db_session.scalars(
                select(NotificationDelivery).order_by(NotificationDelivery.channel)
            )
        ).all()
    )
    assert topics == ["notify.email", "notify.telegram"]
    assert [(delivery.channel, delivery.status) for delivery in deliveries] == [
        ("email", "pending"),
        ("telegram", "pending"),
    ]


@pytest.mark.parametrize(
    ("telegram", "verified_email", "topic"),
    [(True, False, "notify.telegram"), (False, True, "notify.email")],
)
async def test_success_uses_only_linked_available_channel(
    db_session: AsyncSession, telegram: bool, verified_email: bool, topic: str
) -> None:
    order = await _order(db_session, telegram=telegram, verified_email=verified_email)

    await NotificationService(db_session).enqueue_payment_event(order.id, "payment_succeeded")
    await db_session.commit()

    assert list((await db_session.scalars(select(OutboxMessage.topic))).all()) == [topic]


async def test_terminal_delivery_failure_is_durably_queryable(db_session: AsyncSession) -> None:
    """Closing a terminal outbox retry without changing delivery state hides a failed notice."""
    order = await _order(db_session, telegram=True, verified_email=False)
    await NotificationService(db_session).enqueue_payment_event(order.id, "payment_succeeded")
    message = await db_session.scalar(select(OutboxMessage))
    assert message is not None
    message.attempts = MAX_ATTEMPTS - 1
    await db_session.commit()
    dispatcher = OutboxDispatcher()

    async def unavailable(_: dict[str, object]) -> None:
        raise RuntimeError("telegram unavailable")

    dispatcher.register("notify.telegram", unavailable)
    await dispatcher.process(db_session)

    delivery = await db_session.scalar(select(NotificationDelivery))
    assert delivery is not None
    assert delivery.status == "failed"
    assert delivery.error == "telegram unavailable"
