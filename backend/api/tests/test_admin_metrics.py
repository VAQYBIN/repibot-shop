"""Маршрут сводки: кому он открыт, что отдаёт и как на нём работает период."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
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

pytestmark = pytest.mark.docker


async def _seed(engine: AsyncEngine, *, fulfilled_at: datetime, amount: str) -> None:
    """Один исполненный заказ, одна активная подписка, одно ждущее обращение.

    Строки вставляются напрямую: маршрут сводки только читает, и заводить их
    через оплату и поддержку значило бы ронять его тест вместе с чужими.
    """
    async with create_session_factory(engine)() as session:
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
        user = User(email="metrics@example.org", referral_code="metricsA")
        session.add_all([plan, user])
        await session.flush()

        session.add_all(
            [
                Order(
                    user_id=user.id,
                    purpose=OrderPurpose.purchase,
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
                    expires_at=fulfilled_at + timedelta(minutes=30),
                    status=OrderStatus.fulfilled,
                    fulfilled_at=fulfilled_at,
                ),
                Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    status=SubscriptionState.active,
                    started_at=fulfilled_at,
                    expires_at=fulfilled_at + timedelta(days=30),
                    source=SubscriptionSource.purchase,
                ),
                Ticket(
                    user_id=user.id, status=TicketStatus.waiting_staff, subject="Не открывается"
                ),
            ]
        )
        await session.commit()


async def test_support_does_not_see_the_money(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Сводка — это выручка. Поддержке она не положена по разграничению прав."""
    response = await api_client.get("/api/admin/metrics?period=today", headers=support_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_sees_all_six_numbers(
    api_client: AsyncClient, admin_headers: dict[str, str], engine: AsyncEngine
) -> None:
    """Выручка уходит строкой: десятичным деньгам нельзя ехать через float.

    JSON не различает 199.50 и ближайшее к нему двоичное приближение, и
    округление копеек происходило бы уже на стороне браузера.
    """
    await _seed(engine, fulfilled_at=datetime.now(UTC), amount="199.50")

    response = await api_client.get("/api/admin/metrics?period=today", headers=admin_headers)

    assert response.status_code == 200
    assert response.json() == {
        "revenue_rub": "199.50",
        "payments": 1,
        "new_subscriptions": 1,
        "renewals": 0,
        "active_subscriptions": 1,
        "tickets_waiting": 1,
    }


async def test_period_reaches_the_calculation(
    api_client: AsyncClient, admin_headers: dict[str, str], engine: AsyncEngine
) -> None:
    """Иначе переключатель периода врал бы: подпись меняется, числа прежние."""
    await _seed(engine, fulfilled_at=datetime.now(UTC) - timedelta(days=10), amount="199.50")

    today = await api_client.get("/api/admin/metrics?period=today", headers=admin_headers)
    month = await api_client.get("/api/admin/metrics?period=month", headers=admin_headers)

    assert today.json()["revenue_rub"] == "0.00"
    assert today.json()["payments"] == 0
    assert month.json()["revenue_rub"] == "199.50"
    assert month.json()["payments"] == 1


async def test_unknown_period_is_rejected(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Опечатка в периоде — отказ, а не пустая сводка: ноль выручки и
    непонятый запрос выглядят одинаково, но значат разное."""
    response = await api_client.get("/api/admin/metrics?period=year", headers=admin_headers)

    assert response.status_code == 422
