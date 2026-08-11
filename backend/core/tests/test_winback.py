"""Лесенка возврата: ступени, подарки и защита от повторов."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import (
    OneTimeToken,
    Plan,
    Subscription,
    SubscriptionSource,
    TokenType,
    TrafficResetStrategy,
    User,
    WinbackGrant,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.errors import ServiceError
from repibot_core.services.winback import WinbackService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"
# Ступень бесплатных дней при умолчании порогов: та же, что положит в токен крон.
DAYS_STEP = 3


async def _plan(
    session: AsyncSession,
    code: str,
    price_rub: str,
    *,
    is_trial: bool = False,
    is_active: bool = True,
    is_visible: bool = True,
) -> Plan:
    return await PlanRepository(session).create(
        code=code,
        name={"ru": code, "en": code},
        description=None,
        duration_days=30,
        price_rub=Decimal(price_rub),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD],
        is_trial=is_trial,
        is_active=is_active,
        is_visible=is_visible,
        sort_order=0,
    )


async def _user(session: AsyncSession, telegram_id: int, code: str) -> User:
    user = User(email=None, telegram_id=telegram_id, referral_code=code)
    session.add(user)
    await session.flush()
    return user


async def test_same_telegram_cannot_take_a_step_twice(db_session: AsyncSession) -> None:
    """Новая регистрация не должна обнулять счёт: ключ — Telegram, не аккаунт."""
    for _ in range(2):
        db_session.add(WinbackGrant(telegram_id=200_001, user_id=None, step=2, days=0))

    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_user_without_telegram_is_counted_by_account(db_session: AsyncSession) -> None:
    """Почтовый аккаунт тоже нужно ограничить, иначе лесенка бесконечна."""
    user = User(
        email="wb@example.org", email_verified_at=datetime.now(UTC), referral_code="wb00001"
    )
    db_session.add(user)
    await db_session.flush()
    for _ in range(2):
        db_session.add(WinbackGrant(telegram_id=None, user_id=user.id, step=2, days=0))

    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_free_days_token_works_once(db_session: AsyncSession) -> None:
    """Кнопка в письме нажимается дважды: пальцем и почтовым сканером ссылок."""
    await _plan(db_session, "month", "300.00")
    user = await _user(db_session, 200_010, "wbclaim")
    await db_session.commit()
    service = WinbackService(db_session)
    token = await service.issue_days_token(user.id, step=DAYS_STEP)
    await db_session.commit()

    granted = await service.claim_days(token, user.id)
    await db_session.commit()
    with pytest.raises(ServiceError) as second:
        await service.claim_days(token, user.id)

    assert granted == get_settings().winback_free_days
    assert second.value.code == "invalid_token"


async def test_token_of_another_person_is_refused(db_session: AsyncSession) -> None:
    """Токен доказывает право на подарок, но не личность: письмо могло уехать дальше."""
    await _plan(db_session, "month", "300.00")
    owner = await _user(db_session, 200_011, "wbowner")
    stranger = await _user(db_session, 200_012, "wbstrgr")
    await db_session.commit()
    service = WinbackService(db_session)
    token = await service.issue_days_token(owner.id, step=DAYS_STEP)
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await service.claim_days(token, stranger.id)

    assert refusal.value.code == "invalid_token"


async def test_stale_token_is_refused(db_session: AsyncSession) -> None:
    """Кнопка без срока превращается в вечный купон, найденный в архиве переписки."""
    await _plan(db_session, "month", "300.00")
    user = await _user(db_session, 200_013, "wbstale")
    await db_session.commit()
    service = WinbackService(db_session)
    token = await service.issue_days_token(user.id, step=DAYS_STEP)
    issued = await db_session.scalar(select(OneTimeToken))
    assert issued is not None
    issued.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await service.claim_days(token, user.id)

    assert refusal.value.code == "invalid_token"


async def test_token_of_another_kind_gives_no_days(db_session: AsyncSession) -> None:
    """Подтверждение почты не должно работать кнопкой подарка."""
    await _plan(db_session, "month", "300.00")
    user = await _user(db_session, 200_014, "wbkind")
    raw = "чужой-по-назначению-токен"
    db_session.add(
        OneTimeToken(
            type=TokenType.email_verify,
            user_id=user.id,
            token_hash=sha256(raw.encode()).hexdigest(),
            payload={"days": 30, "step": DAYS_STEP},
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await WinbackService(db_session).claim_days(raw, user.id)

    assert refusal.value.code == "invalid_token"


async def test_token_without_step_is_refused(db_session: AsyncSession) -> None:
    """Ступень нужна для записи выдачи: угаданная ступень испортила бы кулдаун."""
    await _plan(db_session, "month", "300.00")
    user = await _user(db_session, 200_015, "wbempty")
    raw = "токен-без-содержимого"
    db_session.add(
        OneTimeToken(
            type=TokenType.winback_days,
            user_id=user.id,
            token_hash=sha256(raw.encode()).hexdigest(),
            payload=None,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await WinbackService(db_session).claim_days(raw, user.id)

    assert refusal.value.code == "invalid_token"


async def test_days_land_on_the_cheapest_visible_paid_plan(db_session: AsyncSession) -> None:
    """У человека может не быть подписки вовсе, а начислять дни некуда."""
    await _plan(db_session, "trial", "0.00", is_trial=True)
    await _plan(db_session, "hidden", "10.00", is_visible=False)
    await _plan(db_session, "retired", "20.00", is_active=False)
    cheapest = await _plan(db_session, "month", "300.00")
    await _plan(db_session, "year", "3000.00")
    user = await _user(db_session, 200_016, "wbnoplan")
    await db_session.commit()
    service = WinbackService(db_session)
    token = await service.issue_days_token(user.id, step=DAYS_STEP)
    await db_session.commit()

    await service.claim_days(token, user.id)
    await db_session.commit()

    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    assert subscription is not None
    assert subscription.plan_id == cheapest.id


async def test_days_extend_the_plan_the_person_already_has(db_session: AsyncSession) -> None:
    """Подарок продлевает то, что куплено, а не переводит на дешёвый тариф."""
    await _plan(db_session, "month", "300.00")
    owned = await _plan(db_session, "year", "3000.00")
    user = await _user(db_session, 200_017, "wbowned")
    expires_at = datetime.now(UTC) + timedelta(days=10)
    db_session.add(
        Subscription(
            user_id=user.id,
            plan_id=owned.id,
            status=SubscriptionState.active,
            started_at=datetime.now(UTC) - timedelta(days=1),
            expires_at=expires_at,
            source=SubscriptionSource.purchase,
            entitlement_price_rub=Decimal("3000.00"),
            entitlement_duration_days=365,
        )
    )
    await db_session.commit()
    service = WinbackService(db_session)
    token = await service.issue_days_token(user.id, step=DAYS_STEP)
    await db_session.commit()

    granted = await service.claim_days(token, user.id)
    await db_session.commit()

    subscription = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    assert subscription is not None
    assert subscription.plan_id == owned.id
    assert subscription.expires_at == expires_at + timedelta(days=granted)


async def test_claim_records_the_step_it_paid_for(db_session: AsyncSession) -> None:
    """Кулдаун считается по выдачам: неучтённый подарок открывает вторую лесенку."""
    await _plan(db_session, "month", "300.00")
    user = await _user(db_session, 200_018, "wbgrant")
    await db_session.commit()
    service = WinbackService(db_session)
    token = await service.issue_days_token(user.id, step=DAYS_STEP)
    await db_session.commit()

    await service.claim_days(token, user.id)
    await db_session.commit()

    grant = await db_session.scalar(select(WinbackGrant))
    assert grant is not None
    assert (grant.telegram_id, grant.user_id, grant.step, grant.days) == (
        200_018,
        user.id,
        DAYS_STEP,
        get_settings().winback_free_days,
    )


async def test_claim_fills_in_the_grant_left_by_the_ladder(db_session: AsyncSession) -> None:
    """Ступень записывается ещё при отправке письма — второй строке взяться неоткуда."""
    await _plan(db_session, "month", "300.00")
    user = await _user(db_session, 200_019, "wbstaged")
    db_session.add(WinbackGrant(telegram_id=200_019, user_id=user.id, step=DAYS_STEP, days=0))
    await db_session.commit()
    service = WinbackService(db_session)
    token = await service.issue_days_token(user.id, step=DAYS_STEP)
    await db_session.commit()

    await service.claim_days(token, user.id)
    await db_session.commit()

    grants = list((await db_session.scalars(select(WinbackGrant))).all())
    assert len(grants) == 1
    assert grants[0].days == get_settings().winback_free_days


async def test_two_simultaneous_clicks_pay_once(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Почтовый сканер ссылок ходит вместе с человеком, и оба приходят разом."""
    await _plan(db_session, "month", "300.00")
    user = await _user(db_session, 200_020, "wbrace")
    await db_session.commit()
    token = await WinbackService(db_session).issue_days_token(user.id, step=DAYS_STEP)
    await db_session.commit()
    user_id = user.id
    factory = create_session_factory(engine)

    async def claim() -> int:
        async with factory() as session:
            days = await WinbackService(session).claim_days(token, user_id)
            await session.commit()
            return days

    outcomes = await asyncio.gather(claim(), claim(), return_exceptions=True)

    paid = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, ServiceError)]
    assert paid == [get_settings().winback_free_days]
    assert [error.code for error in refused] == ["invalid_token"]
