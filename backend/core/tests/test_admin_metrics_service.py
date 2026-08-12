"""Сводка админки: границы периода, что считается деньгами и что — состоянием."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Order,
    OrderPurpose,
    OrderStatus,
    Plan,
    Subscription,
    SubscriptionSource,
    Ticket,
    TicketStatus,
    TrafficResetStrategy,
    User,
)
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.admin_metrics import MetricsPeriod, collect_metrics

pytestmark = pytest.mark.docker


async def _plan(session: AsyncSession) -> Plan:
    """Один тариф на весь тест: сводка на тариф не смотрит, второй ничего не проверял бы."""
    found = await session.scalar(select(Plan).limit(1))
    if found is not None:
        return found
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


async def _user(session: AsyncSession, *, code: str = "metrics1") -> User:
    found = await session.scalar(select(User).where(User.referral_code == code))
    if found is not None:
        return found
    user = User(email=f"{code}@example.org", referral_code=code)
    session.add(user)
    await session.flush()
    return user


async def _order(
    session: AsyncSession,
    *,
    at: datetime | None,
    amount: str,
    purpose: OrderPurpose = OrderPurpose.purchase,
    status: OrderStatus = OrderStatus.fulfilled,
) -> Order:
    """Заказ вставляется строкой: путь через оплату тянул бы за собой провайдера.

    `client_key` случайный — уникальность на пару «пользователь и ключ» иначе
    роняла бы второй заказ теста ещё до подсчёта.
    """
    plan = await _plan(session)
    user = await _user(session)
    order = Order(
        user_id=user.id,
        purpose=purpose,
        plan_id=plan.id,
        plan_code_snapshot=plan.code,
        plan_name_snapshot=dict(plan.name),
        duration_days_snapshot=plan.duration_days,
        price_rub_snapshot=plan.price_rub,
        price_stars_snapshot=plan.price_stars,
        gross_rub=Decimal(amount),
        discount_rub=Decimal("0.00"),
        amount_due_rub=Decimal(amount),
        client_key=uuid4().hex,
        expires_at=(at or datetime.now(UTC)) + timedelta(minutes=30),
        status=status,
        fulfilled_at=at,
    )
    session.add(order)
    await session.flush()
    return order


async def _fulfilled_order(
    session: AsyncSession,
    *,
    at: datetime,
    amount: str,
    purpose: OrderPurpose = OrderPurpose.purchase,
) -> Order:
    return await _order(session, at=at, amount=amount, purpose=purpose)


async def test_orders_outside_the_period_do_not_count(db_session: AsyncSession) -> None:
    """«Сегодня» — это сутки по UTC, как и всё остальное время в системе.

    Заказ, исполненный вчера вечером, не должен попадать в сегодняшнюю
    выручку: по такой цифре нельзя судить, был ли день удачным.
    """
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    await _fulfilled_order(db_session, at=now - timedelta(hours=2), amount="500.00")
    await _fulfilled_order(db_session, at=now - timedelta(hours=20), amount="700.00")

    metrics = await collect_metrics(db_session, MetricsPeriod.today, now=now)

    assert metrics.revenue_rub == Decimal("500.00")
    assert metrics.payments == 1


async def test_week_and_month_count_whole_days(db_session: AsyncSession) -> None:
    """Неделя отсчитывается от полуночи, а не от «сейчас минус семь суток».

    Сотрудник сравнивает дни: заказ позавчерашним утром обязан попасть в
    неделю целиком, независимо от того, в какой час запрошена сводка.
    """
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    await _fulfilled_order(db_session, at=now - timedelta(days=2), amount="100.00")
    await _fulfilled_order(db_session, at=now - timedelta(days=9), amount="200.00")

    week = await collect_metrics(db_session, MetricsPeriod.week, now=now)
    month = await collect_metrics(db_session, MetricsPeriod.month, now=now)

    assert week.revenue_rub == Decimal("100.00")
    assert week.payments == 1
    assert month.revenue_rub == Decimal("300.00")
    assert month.payments == 2


async def test_only_fulfilled_orders_are_money(db_session: AsyncSession) -> None:
    """Ожидающий, просроченный, отменённый и возвращённый заказ деньгами не
    являются: по сумме выставленных счетов нельзя платить зарплату."""
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    at = now - timedelta(hours=1)
    await _fulfilled_order(db_session, at=at, amount="500.00")
    for status in (OrderStatus.pending, OrderStatus.expired, OrderStatus.canceled):
        await _order(db_session, at=None, amount="900.00", status=status)
    # Возвращённый заказ момент исполнения сохраняет: он был исполнен и только
    # потом отменён деньгами назад. Отсеять его может лишь проверка статуса.
    await _order(db_session, at=at, amount="900.00", status=OrderStatus.refunded)

    metrics = await collect_metrics(db_session, MetricsPeriod.today, now=now)

    assert metrics.revenue_rub == Decimal("500.00")
    assert metrics.payments == 1


async def test_purpose_splits_purchases_and_renewals(db_session: AsyncSession) -> None:
    """Подарок — выручка, но ни новая подписка, ни продление.

    Он оплачен не тем, кто им воспользуется, и день активации неизвестен:
    считать его новой подпиской значит завышать приток.
    """
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    at = now - timedelta(hours=1)
    await _fulfilled_order(db_session, at=at, amount="300.00", purpose=OrderPurpose.purchase)
    await _fulfilled_order(db_session, at=at, amount="200.00", purpose=OrderPurpose.renew)
    await _fulfilled_order(db_session, at=at, amount="100.00", purpose=OrderPurpose.gift)

    metrics = await collect_metrics(db_session, MetricsPeriod.today, now=now)

    assert metrics.revenue_rub == Decimal("600.00")
    assert metrics.payments == 3
    assert metrics.new_subscriptions == 1
    assert metrics.renewals == 1


async def test_state_tiles_ignore_the_period(db_session: AsyncSession) -> None:
    """Активные подписки и ждущие ответа обращения — это «сейчас», а не «за
    период»: иначе «активные подписки за сегодня» читается как «появившиеся
    сегодня»."""
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    long_ago = now - timedelta(days=200)
    plan = await _plan(db_session)
    subscriber = await _user(db_session, code="metrics1")
    expired_subscriber = await _user(db_session, code="metrics2")
    db_session.add_all(
        [
            Subscription(
                user_id=subscriber.id,
                plan_id=plan.id,
                status=SubscriptionState.active,
                started_at=long_ago,
                expires_at=now + timedelta(days=10),
                source=SubscriptionSource.purchase,
            ),
            Subscription(
                user_id=expired_subscriber.id,
                plan_id=plan.id,
                status=SubscriptionState.expired,
                started_at=long_ago,
                expires_at=long_ago + timedelta(days=30),
                source=SubscriptionSource.purchase,
            ),
            Ticket(
                user_id=subscriber.id,
                status=TicketStatus.waiting_staff,
                subject="Не открывается",
                created_at=long_ago,
            ),
            Ticket(
                user_id=subscriber.id,
                status=TicketStatus.closed,
                subject="Уже разобрались",
                created_at=long_ago,
            ),
        ]
    )
    await db_session.flush()

    for period in MetricsPeriod:
        metrics = await collect_metrics(db_session, period, now=now)

        assert metrics.active_subscriptions == 1, period
        assert metrics.tickets_waiting == 1, period


async def test_empty_base_gives_zeros(db_session: AsyncSession) -> None:
    """Пустая база — это нули, а не отсутствующая выручка: плитке нечего было
    бы показать, а `None` в деньгах пришлось бы разбирать каждому вызывающему."""
    metrics = await collect_metrics(db_session, MetricsPeriod.month)

    assert metrics.revenue_rub == Decimal("0.00")
    assert metrics.payments == 0
    assert metrics.new_subscriptions == 0
    assert metrics.renewals == 0
    assert metrics.active_subscriptions == 0
    assert metrics.tickets_waiting == 0
