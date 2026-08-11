"""Надёжная рассылка событий оплаты во все привязанные каналы."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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


async def test_delivery_exists_without_an_order(db_session: AsyncSession) -> None:
    """Ни одно уведомление подпроекта 4 не связано с заказом.

    Обязательный order_id означал бы, что напоминание об истечении нужно
    привязывать к выдуманному заказу — и первый же отчёт по деньгам стал бы
    врать.
    """
    user = User(email=None, telegram_id=100_777, referral_code="freekey1")
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        NotificationDelivery(
            user_id=user.id, kind="expiring_3", channel="telegram", dedup_key="sub:1:expiring:3:x"
        )
    )
    await db_session.commit()

    stored = await db_session.scalar(select(NotificationDelivery))
    assert stored is not None
    assert stored.order_id is None
    assert stored.dedup_key == "sub:1:expiring:3:x"


async def test_same_key_and_channel_cannot_be_staged_twice(db_session: AsyncSession) -> None:
    """Повторный запуск крона не должен слать второе напоминание."""
    user = User(email=None, telegram_id=100_778, referral_code="freekey2")
    db_session.add(user)
    await db_session.flush()
    for _ in range(2):
        db_session.add(
            NotificationDelivery(
                user_id=user.id, kind="expired", channel="email", dedup_key="sub:2:expired:x"
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_success_enqueues_each_available_channel_once(db_session: AsyncSession) -> None:
    """Потеря адресата или уникальности доставки обязана уронить этот тест."""
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
    """Закрыть попытку очереди, не тронув доставку, значит спрятать неудачу."""
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


async def test_telegram_delivery_refuses_to_build_its_own_client(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Клиент бота живёт прогон задачи, а не сообщение.

    Собирать соединение с Valkey и http-клиент на каждое уведомление значит
    платить ими за каждое: разбор очереди берёт до двадцати сообщений за раз.
    Отсутствие клиента — ошибка сборки, и она должна быть громкой, а не
    молча возвращать прежнее поведение.
    """
    from repibot_core.db.engine import create_session_factory
    from repibot_core.services.dispatcher import build_dispatcher

    order = await _order(db_session, telegram=True, verified_email=False)
    await NotificationService(db_session).enqueue_payment_event(order.id, "payment_succeeded")
    await db_session.commit()
    factory = create_session_factory(engine)

    await build_dispatcher(factory).process(db_session)

    message = await db_session.scalar(
        select(OutboxMessage).where(OutboxMessage.topic == "notify.telegram")
    )
    assert message is not None
    assert message.processed_at is None
    assert message.attempts == 1
    # Обработчик не пробует достучаться до Telegram своими силами, а называет
    # причину: собранный на месте клиент выглядел бы рабочим решением.
    assert "клиент бота" in (message.last_error or "")
