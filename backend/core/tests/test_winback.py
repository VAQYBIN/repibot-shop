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
    NotificationDelivery,
    OneTimeToken,
    OutboxMessage,
    Plan,
    PromoCode,
    Subscription,
    SubscriptionSource,
    TokenType,
    TrafficResetStrategy,
    User,
    WinbackGrant,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.i18n import translate
from repibot_core.services.errors import ServiceError
from repibot_core.services.notifications import PAYLOAD_KEYS, resolve_kind
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


# --- суточный обход лесенки ---


async def _expired_subscriber(
    session: AsyncSession, *, days_ago: int, telegram_id: int
) -> Subscription:
    """Ушедший человек со своим тарифом.

    Тариф свой у каждого: код тарифа уникален, а подписка одна на человека,
    поэтому наборы не могут делить ни то, ни другое.
    """
    user = await _user(session, telegram_id, f"wb{telegram_id}")
    plan = await _plan(session, f"back{telegram_id}", "300.00")
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.expired,
        started_at=datetime.now(UTC) - timedelta(days=days_ago + 30),
        expires_at=datetime.now(UTC) - timedelta(days=days_ago),
        auto_renew_enabled=False,
        source=SubscriptionSource.purchase,
        entitlement_price_rub=Decimal("300.00"),
        entitlement_duration_days=30,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def _kinds(session: AsyncSession) -> list[str]:
    return list(
        (
            await session.scalars(
                select(NotificationDelivery.kind).order_by(NotificationDelivery.id)
            )
        ).all()
    )


async def test_ladder_walks_its_steps_once_each(db_session: AsyncSession) -> None:
    """Четыре касания за месяц, каждое по одному разу на дату истечения."""
    subscription = await _expired_subscriber(db_session, days_ago=1, telegram_id=200_030)
    await db_session.commit()
    service = WinbackService(db_session)

    first = await service.run(now=datetime.now(UTC))
    again = await service.run(now=datetime.now(UTC))
    await db_session.commit()

    assert (first, again) == (1, 0)
    assert await _kinds(db_session) == ["winback_1"]
    assert subscription.id > 0


async def test_ladder_reaches_every_step_and_every_text_gets_its_substitutions(
    db_session: AsyncSession,
) -> None:
    """Лесенка доходит до конца, и каждый текст собирается из того, что она положила."""
    subscription = await _expired_subscriber(db_session, days_ago=1, telegram_id=200_031)
    await db_session.commit()
    service = WinbackService(db_session)
    settings = get_settings()

    staged = [
        await service.run(now=subscription.expires_at + timedelta(days=offset, hours=9))
        for offset in sorted(settings.winback_steps_days)
    ]
    await db_session.commit()

    assert staged == [1, 1, 1, 1]
    assert await _kinds(db_session) == ["winback_1", "winback_2", "winback_3", "winback_4"]
    payloads = {
        str(message.payload["kind"]): message.payload
        for message in (await db_session.scalars(select(OutboxMessage))).all()
    }
    for kind, payload in payloads.items():
        params = {key: value for key, value in payload.items() if key not in PAYLOAD_KEYS}
        for language in ("ru", "en"):
            for variant in ("bot", "subject", "body"):
                assert translate(language, f"{resolve_kind(kind).text_key}.{variant}", **params)
    assert payloads["winback_2"]["percent"] == settings.winback_promo_percent
    assert payloads["winback_3"]["days"] == settings.winback_free_days
    assert str(payloads["winback_3"]["link"]).startswith(
        f"{settings.public_app_url}/winback?token="
    )


async def test_active_subscription_stops_the_ladder(db_session: AsyncSession) -> None:
    """Человек вернулся — предлагать ему вернуться незачем."""
    subscription = await _expired_subscriber(db_session, days_ago=3, telegram_id=200_032)
    subscription.status = SubscriptionState.active
    subscription.expires_at = datetime.now(UTC) + timedelta(days=30)
    await db_session.commit()

    staged = await WinbackService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0


async def test_opted_out_user_gets_no_ladder(db_session: AsyncSession) -> None:
    subscription = await _expired_subscriber(db_session, days_ago=1, telegram_id=200_033)
    user = await db_session.get(User, subscription.user_id)
    assert user is not None
    user.marketing_opt_out_at = datetime.now(UTC)
    await db_session.commit()

    staged = await WinbackService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0


async def test_cooldown_blocks_a_second_ladder(db_session: AsyncSession) -> None:
    """Полгода между лесенками: иначе истечение превращается в способ заработка."""
    subscription = await _expired_subscriber(db_session, days_ago=1, telegram_id=200_034)
    db_session.add(
        WinbackGrant(
            telegram_id=200_034,
            user_id=subscription.user_id,
            step=2,
            days=0,
            # Выдача прошлой лесенки: она случилась до того, как эта подписка
            # кончилась. Отметка «сегодня» описывала бы выдачу текущей лесенки.
            granted_at=subscription.expires_at - timedelta(days=30),
        )
    )
    await db_session.commit()

    staged = await WinbackService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0


async def test_ladder_of_last_year_does_not_block_the_next_one(db_session: AsyncSession) -> None:
    """Через полгода лесенка идёт вторым кругом и переписывает собственную строку.

    Новая строка на ту же ступень не встала бы под уникальный индекс и уронила
    бы весь прогон крона, а не одного человека.
    """
    subscription = await _expired_subscriber(db_session, days_ago=3, telegram_id=200_035)
    db_session.add(
        WinbackGrant(
            telegram_id=200_035,
            user_id=subscription.user_id,
            step=2,
            days=0,
            granted_at=subscription.expires_at - timedelta(days=400),
        )
    )
    await db_session.commit()

    staged = await WinbackService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    grants = list((await db_session.scalars(select(WinbackGrant))).all())
    assert (staged, await _kinds(db_session)) == (1, ["winback_2"])
    assert len(grants) == 1
    # Отметка обязана переехать на свежую выдачу: со старой третья лесенка
    # пришла бы сразу за второй.
    assert grants[0].granted_at > subscription.expires_at


async def test_long_gone_subscriber_gets_no_ladder(db_session: AsyncSession) -> None:
    """Пропущенные сутки не должны превращаться в рассылку по всем, кто ушёл когда-то."""
    await _expired_subscriber(db_session, days_ago=400, telegram_id=200_036)
    await db_session.commit()

    staged = await WinbackService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert (staged, await _kinds(db_session)) == (0, [])


async def test_repeated_run_mints_no_second_promo(db_session: AsyncSession) -> None:
    """Второй прогон в те же сутки не должен плодить коды: письмо-то уже поставлено."""
    subscription = await _expired_subscriber(db_session, days_ago=3, telegram_id=200_037)
    await db_session.commit()
    service = WinbackService(db_session)

    first = await service.run(now=datetime.now(UTC))
    again = await service.run(now=datetime.now(UTC))
    await db_session.commit()

    promos = list((await db_session.scalars(select(PromoCode))).all())
    assert (first, again) == (1, 0)
    assert len(promos) == 1
    # Код личный: чужому он отвечает то же, что и несуществующий.
    assert promos[0].target_user_id == subscription.user_id
    assert promos[0].percent_off == get_settings().winback_promo_percent
