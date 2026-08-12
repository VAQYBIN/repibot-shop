"""Числа сводки админки: деньги за период и состояние на сейчас.

Считается по нашей базе, в панель не ходит: панель знает про доступ, а не про
оплаты, и её недоступность не должна оставлять владельца без выручки.

Деньгами считается только исполненный заказ. Ожидающий, просроченный,
отменённый и возвращённый — это выставленные и не полученные счета, и складывать
их в выручку значит показывать деньги, которых нет.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Order,
    OrderPurpose,
    OrderStatus,
    Subscription,
    Ticket,
    TicketStatus,
)
from repibot_core.domain.subscriptions import SubscriptionState


class MetricsPeriod(StrEnum):
    """Период сводки. Перечисление, а не пара дат.

    Произвольный период — это календарь, валидация порядка дат и разговор о
    часовых поясах; сводка из шести чисел его не стоит.
    """

    today = "today"
    week = "week"
    month = "month"


# Сколько суток назад от сегодняшней полуночи начинается период.
_PERIOD_DAYS: dict[MetricsPeriod, int] = {
    MetricsPeriod.today: 0,
    MetricsPeriod.week: 7,
    MetricsPeriod.month: 30,
}


@dataclass(frozen=True, slots=True)
class Metrics:
    """Шесть чисел плиток. Первые четыре — за период, последние два — на сейчас."""

    revenue_rub: Decimal
    payments: int
    new_subscriptions: int
    renewals: int
    active_subscriptions: int
    tickets_waiting: int


def period_start(period: MetricsPeriod, now: datetime) -> datetime:
    """Начало периода — полночь UTC, а не «сейчас минус сутки».

    Сотрудник сравнивает дни, а не скользящие окна: при отсчёте от момента
    запроса «сегодня» в десять утра означало бы половину вчерашнего дня, и две
    сводки подряд давали бы разные числа за один и тот же день.
    """
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=_PERIOD_DAYS[period])


async def collect_metrics(
    session: AsyncSession, period: MetricsPeriod, *, now: datetime | None = None
) -> Metrics:
    """Собирает сводку за период.

    Момент отсчёта принимается параметром: без него проверка границ периода
    зависела бы от времени суток, в которое её запустили.
    """
    since = period_start(period, now if now is not None else datetime.now(UTC))

    # Одним запросом с группировкой по назначению: сумма, число оплат, новые
    # подписки и продления живут в одной таблице, и четыре прохода по ней ради
    # четырёх чисел означали бы четыре одинаковых сканирования.
    #
    # Верхней границы нет намеренно. Заказ, исполненный на долю секунды позже
    # прочитанного момента, — это гонка между записью и отчётом, а не будущее:
    # отсечка по `now` теряла бы такую оплату из сегодняшней выручки.
    grouped = await session.execute(
        select(Order.purpose, func.count(Order.id), func.sum(Order.amount_due_rub))
        .where(Order.status == OrderStatus.fulfilled, Order.fulfilled_at >= since)
        .group_by(Order.purpose)
    )

    # Ноль — Decimal, а не 0.0: деньгам нельзя ехать через число с плавающей
    # точкой даже в пустой базе, иначе тип результата зависит от наличия строк.
    revenue = Decimal("0.00")
    payments = 0
    counted: dict[OrderPurpose, int] = {}
    for purpose, orders, amount in grouped.all():
        count = int(orders)
        revenue += Decimal(amount)
        payments += count
        counted[OrderPurpose(purpose)] = count

    active = await session.scalar(
        select(func.count())
        .select_from(Subscription)
        .where(Subscription.status == SubscriptionState.active)
    )
    waiting = await session.scalar(
        select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.waiting_staff)
    )

    return Metrics(
        revenue_rub=revenue,
        payments=payments,
        # Подарок в выручку входит, но новой подпиской не считается: оплатил его
        # не тот, кто им воспользуется, и когда воспользуется — неизвестно.
        new_subscriptions=counted.get(OrderPurpose.purchase, 0),
        renewals=counted.get(OrderPurpose.renew, 0),
        active_subscriptions=int(active or 0),
        tickets_waiting=int(waiting or 0),
    )
