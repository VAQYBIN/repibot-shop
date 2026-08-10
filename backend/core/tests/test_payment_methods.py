"""Действующая карта пользователя одна, и она управляет автоплатежом."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    SavedPaymentMethod,
    Subscription,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.payment_methods import PaymentMethodService

pytestmark = pytest.mark.docker


async def _subscriber(session: AsyncSession, code: str) -> User:
    plan = await PlanRepository(session).create(
        code=f"plan-{code}",
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
    user = User(email=f"{code}@example.org", referral_code=code)
    session.add(user)
    await session.flush()
    session.add(
        Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionState.active,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=30),
            source=SubscriptionSource.purchase,
            entitlement_price_rub=plan.price_rub,
            entitlement_duration_days=plan.duration_days,
        )
    )
    await session.commit()
    return user


async def _active_count(session: AsyncSession, user_id: int) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(SavedPaymentMethod)
        .where(
            SavedPaymentMethod.user_id == user_id,
            SavedPaymentMethod.revoked_at.is_(None),
        )
    )
    return int(total or 0)


async def _auto_renew(session: AsyncSession, user_id: int) -> bool:
    value = await session.scalar(
        select(Subscription.auto_renew_enabled).where(Subscription.user_id == user_id)
    )
    return bool(value)


async def test_saving_a_card_replaces_the_previous_one(db_session: AsyncSession) -> None:
    """Две действующие карты означали бы списание с забытой пользователем."""
    user = await _subscriber(db_session, "cards001")
    methods = PaymentMethodService(db_session)

    await methods.save(user.id, provider_method_id="m1", title="Bank card *1111")
    await methods.save(user.id, provider_method_id="m2", title="Bank card *4444")
    await db_session.commit()

    current = await methods.current(user.id)
    assert current is not None and current.title == "Bank card *4444"
    assert await methods.current_method_id(user.id) == "m2"
    assert await _active_count(db_session, user.id) == 1


async def test_saving_a_card_turns_auto_renew_on(db_session: AsyncSession) -> None:
    """Галочка на форме и есть согласие на повторные списания."""
    user = await _subscriber(db_session, "cards002")
    assert await _auto_renew(db_session, user.id) is False

    await PaymentMethodService(db_session).save(
        user.id, provider_method_id="m1", title="Bank card *4444"
    )
    await db_session.commit()

    assert await _auto_renew(db_session, user.id) is True


async def test_revoking_the_card_turns_auto_renew_off_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    """Автоплатёж без карты обещал бы списание, которого не будет."""
    user = await _subscriber(db_session, "cards003")
    methods = PaymentMethodService(db_session)
    await methods.save(user.id, provider_method_id="m1", title="Bank card *4444")
    await db_session.commit()

    assert await methods.revoke(user.id) is True
    await db_session.commit()

    assert await methods.current(user.id) is None
    assert await _auto_renew(db_session, user.id) is False
    assert await methods.revoke(user.id) is False


async def test_revoked_cards_do_not_block_a_later_one(db_session: AsyncSession) -> None:
    """Частичный индекс обязан считать погашенные строки несуществующими."""
    user = await _subscriber(db_session, "cards004")
    methods = PaymentMethodService(db_session)
    await methods.save(user.id, provider_method_id="m1", title="Bank card *1111")
    await methods.revoke(user.id)
    await methods.save(user.id, provider_method_id="m2", title="Bank card *4444")
    await db_session.commit()

    assert await methods.current_method_id(user.id) == "m2"
    assert await _active_count(db_session, user.id) == 1
