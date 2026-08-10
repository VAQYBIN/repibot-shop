"""Промокоды: резервы, лимиты и снимок цены заказа."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import (
    Order,
    OrderPurpose,
    Plan,
    PromoReservation,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.services.promotions import PromotionInput, PromotionService

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _user(session: AsyncSession, code: str) -> User:
    user = User(email=f"{code}@example.org", referral_code=code)
    session.add(user)
    await session.flush()
    return user


async def _plan(session: AsyncSession, code: str = "month") -> Plan:
    return await PlanRepository(session).create(
        code=code,
        name={"ru": code, "en": code},
        description=None,
        duration_days=30,
        price_rub=Decimal("300.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )


async def _pending_order(session: AsyncSession, user: User, plan: Plan, key: str) -> Order:
    return await OrderRepository(session).create_pending(
        user_id=user.id,
        plan=plan,
        purpose=OrderPurpose.purchase,
        client_key=key,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )


async def test_max_one_promo_use_is_reserved_by_only_one_concurrent_order(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Без блокировки строки два заказа потратили бы последнее применение."""
    plan = await _plan(db_session)
    first_user, second_user = (
        await _user(db_session, "promo001"),
        await _user(db_session, "promo002"),
    )
    promo = await PromotionService(db_session).create(
        PromotionInput(code="ONEUSE", percent_off=10, max_uses=1)
    )
    await db_session.commit()
    factory = create_session_factory(engine)

    async def reserve(user_id: int, key: str) -> str:
        async with factory() as session:
            order = await _pending_order(
                session, first_user if user_id == first_user.id else second_user, plan, key
            )
            try:
                await PromotionService(session).reserve(
                    order=order, user_id=user_id, code=promo.code
                )
            except Exception as error:  # ошибка сервиса и есть наблюдаемый признак недоступности
                await session.rollback()
                return getattr(error, "code", "unexpected")
            await session.commit()
            return "ok"

    results = await asyncio.gather(reserve(first_user.id, "one"), reserve(second_user.id, "two"))

    assert sorted(results) == ["ok", "promo_unavailable"]


async def test_percent_rounding_bonus_days_and_per_user_limit_are_saved_on_reservation(
    db_session: AsyncSession,
) -> None:
    """Правка округления, бонуса или лимита обязана менять исход резервирования."""
    plan = await _plan(db_session)
    user = await _user(db_session, "promo003")
    promo = await PromotionService(db_session).create(
        PromotionInput(code="SAVE", percent_off=33, bonus_days=5, per_user_limit=1)
    )
    first = await _pending_order(db_session, user, plan, "first")
    quote = await PromotionService(db_session).reserve(
        order=first, user_id=user.id, code=promo.code
    )
    await db_session.commit()

    assert quote.discount_rub == Decimal("99.00")
    assert quote.bonus_days == 5
    second = await _pending_order(db_session, user, plan, "second")
    with pytest.raises(Exception, match="промокод"):
        await PromotionService(db_session).reserve(order=second, user_id=user.id, code=promo.code)


async def test_only_pending_expired_reservation_is_released(db_session: AsyncSession) -> None:
    """Удаление погашенных резервов вернуло бы уже оплаченные применения."""
    plan = await _plan(db_session)
    user = await _user(db_session, "promo004")
    promo = await PromotionService(db_session).create(
        PromotionInput(code="TTL", percent_off=10, max_uses=2)
    )
    pending = await _pending_order(db_session, user, plan, "pending")
    used = await _pending_order(db_session, user, plan, "used")
    service = PromotionService(db_session)
    await service.reserve(order=pending, user_id=user.id, code=promo.code)
    await service.reserve(order=used, user_id=user.id, code=promo.code)
    await service.consume(order_id=used.id)
    await db_session.execute(
        update(PromoReservation)
        .where(PromoReservation.order_id == pending.id)
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await service.release_expired(now=datetime.now(UTC))
    rows = list(
        (
            await db_session.scalars(select(PromoReservation).order_by(PromoReservation.order_id))
        ).all()
    )

    assert [row.order_id for row in rows] == [used.id]
    assert rows[0].consumed_at is not None
