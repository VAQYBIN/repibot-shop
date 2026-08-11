"""Напоминания о судьбе подписки."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    NotificationDelivery,
    Plan,
    Subscription,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.i18n import translate
from repibot_core.services.notifications import resolve_kind
from repibot_core.services.payment_methods import PaymentMethodService
from repibot_core.services.subscription_notices import SubscriptionNoticeService
from repibot_core.settings import Settings


def _settings(**overrides: object) -> Settings:
    """Настройки поверх тестового окружения.

    Конструктор читает те же переменные, что и боевой процесс: собирать их
    здесь заново значит проверять сборку, а не разбор значения.
    """
    return Settings(**overrides)  # type: ignore[arg-type]


def test_reminder_days_are_read_from_a_comma_separated_string() -> None:
    """В .env человек пишет список через запятую, а не JSON-массив."""
    assert _settings(EXPIRY_REMINDER_DAYS="3, 1").expiry_reminder_days == (3, 1)


def test_every_threshold_has_a_registered_kind_and_texts() -> None:
    """Порог из .env превращается в вид уведомления, а вид нужно объявить.

    Без этой проверки строка EXPIRY_REMINDER_DAYS=7 роняла бы крон на живом
    стенде: resolve_kind не знает вида expiring_7, а translate — его текстов.
    Поэтому пороги не произвольные, и добавление третьего — это задача.
    """
    for days in _settings().expiry_reminder_days:
        kind = resolve_kind(f"expiring_{days}")
        assert translate("ru", f"{kind.text_key}.bot", plan="Месяц", date="01.01.2026")
        assert translate("en", f"{kind.text_key}.bot", plan="Month", date="01.01.2026")


@pytest.mark.parametrize("value", ["4", "0", "10"])
def test_unregistered_threshold_is_caught_here_and_not_in_production(value: str) -> None:
    """Проверка выше должна ловить чужой порог, а не пропускать его молча."""
    with pytest.raises(KeyError):
        resolve_kind(f"expiring_{value}")


# Ниже — наборы с настоящей базой: дедупликацию обеспечивает уникальный индекс,
# и проверять её на подставном хранилище значит проверять подставное хранилище.
pytestmark = pytest.mark.docker


async def _subscriber(
    session: AsyncSession, *, expires_in: timedelta, status: SubscriptionState, telegram_id: int
) -> Subscription:
    """Человек с подпиской и своим тарифом.

    Тариф свой у каждого: код тарифа уникален, а подписка одна на человека,
    поэтому наборы не могут делить ни то, ни другое.
    """
    user = User(email=None, telegram_id=telegram_id, referral_code=f"note{telegram_id}")
    session.add(user)
    plan = await PlanRepository(session).create(
        code=f"plan{telegram_id}",
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
    await session.flush()
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=status,
        started_at=datetime.now(UTC) - timedelta(days=30),
        expires_at=datetime.now(UTC) + expires_in,
        auto_renew_enabled=False,
        source=SubscriptionSource.purchase,
        entitlement_price_rub=Decimal("299.00"),
        entitlement_duration_days=30,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def _kinds(session: AsyncSession) -> list[str]:
    return list((await session.scalars(select(NotificationDelivery.kind))).all())


async def test_three_day_notice_is_staged_once_per_expiry_date(db_session: AsyncSession) -> None:
    """Перезапуск крона в том же цикле не должен слать второе напоминание."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=2, hours=12),
        status=SubscriptionState.active,
        telegram_id=101_001,
    )
    await db_session.commit()
    service = SubscriptionNoticeService(db_session)

    first = await service.run(now=datetime.now(UTC))
    second = await service.run(now=datetime.now(UTC))
    await db_session.commit()

    assert (first, second) == (1, 0)
    assert await _kinds(db_session) == ["expiring_3"]
    assert subscription.id > 0


async def test_renewal_opens_a_new_cycle_of_notices(db_session: AsyncSession) -> None:
    """Новая дата окончания — новый повод напомнить, а не молчание навсегда."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=2, hours=12),
        status=SubscriptionState.active,
        telegram_id=101_002,
    )
    await db_session.commit()
    service = SubscriptionNoticeService(db_session)
    await service.run(now=datetime.now(UTC))

    subscription.expires_at = datetime.now(UTC) + timedelta(days=32, hours=12)
    await db_session.commit()
    after_renewal = await service.run(now=datetime.now(UTC) + timedelta(days=30))
    await db_session.commit()

    assert after_renewal == 1


async def test_the_last_day_is_told_about_once_and_by_the_urgent_notice(
    db_session: AsyncSession,
) -> None:
    """Подписке с последним днём подходят оба порога, а сказать нужно одно.

    Оба напоминания разом — это «завтра» и «через три дня» в одну минуту;
    человек поверит второму и потеряет доступ.
    """
    await _subscriber(
        db_session,
        expires_in=timedelta(hours=12),
        status=SubscriptionState.active,
        telegram_id=101_007,
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert (staged, await _kinds(db_session)) == (1, ["expiring_1"])


async def test_expired_subscription_gets_its_own_notice(db_session: AsyncSession) -> None:
    await _subscriber(
        db_session,
        expires_in=timedelta(hours=-1),
        status=SubscriptionState.expired,
        telegram_id=101_003,
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert (staged, await _kinds(db_session)) == (1, ["expired"])


async def test_working_auto_renewal_silences_the_expiry_notice(db_session: AsyncSession) -> None:
    """Незачем тревожить окончанием того, что продлится само.

    Если продление не сработает, придёт сообщение о неудаче — оно уже есть.
    """
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=2, hours=12),
        status=SubscriptionState.active,
        telegram_id=101_004,
    )
    # Карта заводится тем же сервисом, что и в бою: он же включает автоплатёж,
    # и собранная руками строка разошлась бы с этой связкой.
    await PaymentMethodService(db_session).save(
        subscription.user_id, provider_method_id="pm-1", title="Bank card *4444"
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0


async def test_auto_renewal_without_a_card_still_gets_the_notice(db_session: AsyncSession) -> None:
    """Включённая настройка без карты — это не автопродление, а надежда.

    Списывать не с чего, доступ прервётся, и промолчать здесь значит оставить
    человека наедине с обещанием, которое некому выполнить.
    """
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=2, hours=12),
        status=SubscriptionState.active,
        telegram_id=101_008,
    )
    subscription.auto_renew_enabled = True
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert (staged, await _kinds(db_session)) == (1, ["expiring_3"])


async def _invoice(
    session: AsyncSession,
    subscription: Subscription,
    *,
    client_key: str,
    age: timedelta,
    ttl: timedelta,
) -> int:
    """Неоплаченный счёт заданного возраста и с заданным остатком срока.

    Возраст проставляется прямой правкой: заказ заводится репозиторием, а тот
    берёт момент создания у базы — и другого способа состарить его нет.
    """
    plan = await session.get(Plan, subscription.plan_id)
    assert plan is not None
    order = await OrderRepository(session).create_pending(
        user_id=subscription.user_id,
        plan=plan,
        client_key=client_key,
        expires_at=datetime.now(UTC) + ttl,
    )
    order.created_at = datetime.now(UTC) - age
    await session.flush()
    return order.id


async def test_unpaid_invoice_is_reminded_once(db_session: AsyncSession) -> None:
    """Одно напоминание на заказ: второе выглядит как требование долга."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=20),
        status=SubscriptionState.active,
        telegram_id=101_005,
    )
    order_id = await _invoice(
        db_session,
        subscription,
        client_key="unpaid-1",
        age=timedelta(minutes=40),
        ttl=timedelta(minutes=30),
    )
    await db_session.commit()
    service = SubscriptionNoticeService(db_session)

    first = await service.run(now=datetime.now(UTC))
    second = await service.run(now=datetime.now(UTC))
    await db_session.commit()

    staged = list(
        (
            await db_session.scalars(
                select(NotificationDelivery.kind).where(NotificationDelivery.order_id == order_id)
            )
        ).all()
    )
    assert (first - second, staged) == (1, ["unpaid_invoice"])


async def test_fresh_invoice_is_left_alone(db_session: AsyncSession) -> None:
    """Человек всё ещё на форме оплаты; торопить его нечем."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=20),
        status=SubscriptionState.active,
        telegram_id=101_006,
    )
    await _invoice(
        db_session,
        subscription,
        client_key="fresh-1",
        age=timedelta(0),
        ttl=timedelta(minutes=30),
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0


async def test_dead_invoice_is_not_advertised(db_session: AsyncSession) -> None:
    """Звать оплатить туда, где платить уже нельзя, хуже, чем промолчать."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=20),
        status=SubscriptionState.active,
        telegram_id=101_009,
    )
    await _invoice(
        db_session,
        subscription,
        client_key="dead-1",
        age=timedelta(minutes=40),
        ttl=timedelta(minutes=-1),
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert (staged, await _kinds(db_session)) == (0, [])


async def test_long_gone_subscriber_is_not_told_his_subscription_ended(
    db_session: AsyncSession,
) -> None:
    """Первый прогон не должен становиться рассылкой по всем, кто ушёл когда-то.

    Ключ дедупликации спасает от повторов, но не от первого раза: без окна
    выкатка этой задачи разослала бы «Подписка закончилась» каждому, кто
    отвалился хоть год назад. Заодно это ежечасный полный проход по таблице,
    которая только растёт.
    """
    await _subscriber(
        db_session,
        expires_in=timedelta(days=-400),
        status=SubscriptionState.expired,
        telegram_id=101_009,
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert (staged, await _kinds(db_session)) == (0, [])
