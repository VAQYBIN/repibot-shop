"""Триал, начисление, смена тарифа, истечение."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    OutboxMessage,
    Plan,
    SubscriptionActor,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError
from repibot_core.services.provisioning import TOPIC_PROVISION, ProvisioningService
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.settings import get_settings
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _plan(session: AsyncSession, code: str, **overrides: object) -> Plan:
    fields: dict[str, object] = {
        "code": code,
        "name": {"ru": code, "en": code},
        "description": None,
        "duration_days": 30,
        "price_rub": Decimal("300.00"),
        "price_stars": 199,
        "traffic_limit_bytes": 0,
        "traffic_reset_strategy": TrafficResetStrategy.NO_RESET,
        "hwid_device_limit": 3,
        "internal_squad_uuids": [SQUAD],
        "is_trial": False,
        "is_active": True,
        "is_visible": True,
        "sort_order": 0,
    }
    fields.update(overrides)
    return await PlanRepository(session).create(**fields)


async def _user(session: AsyncSession, code: str, telegram_id: int | None) -> User:
    user = User(email=f"{code}@example.org", referral_code=code, telegram_id=telegram_id)
    session.add(user)
    await session.flush()
    await session.commit()
    return user


def _service(session: AsyncSession, panel: FakePanel) -> SubscriptionService:
    provisioning = ProvisioningService(session, PanelUsers(panel.client()))
    return SubscriptionService(session, get_settings(), provisioning)


async def test_trial_requires_telegram(db_session: AsyncSession) -> None:
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00001", None)

    with pytest.raises(ServiceError) as error:
        await _service(db_session, FakePanel()).activate_trial(user.id)
    assert error.value.code == "trial_requires_telegram"


async def test_trial_is_given_once_per_telegram(db_session: AsyncSession) -> None:
    """Правило висит на Telegram, а не на аккаунте: аккаунт легко завести заново."""
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    first = await _user(db_session, "sub00002", 4242)
    service = _service(db_session, FakePanel())
    await service.activate_trial(first.id)

    # Уникальность telegram_id не даёт держать два живых аккаунта на один
    # Telegram, поэтому накрутка выглядит как удаление и повторная регистрация.
    # Отметка о выданном триале это переживает — на ней правило и держится.
    await db_session.delete(first)
    await db_session.commit()

    second = await _user(db_session, "sub00003", 4242)
    with pytest.raises(ServiceError) as error:
        await service.activate_trial(second.id)
    assert error.value.code == "trial_already_used"


async def test_own_subscription_is_reported_before_used_trial(db_session: AsyncSession) -> None:
    """Человеку с подпиской честнее сказать «она уже есть», а не «триал выдавался»."""
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00004", 21)
    service = _service(db_session, FakePanel())
    await service.activate_trial(user.id)

    with pytest.raises(ServiceError) as error:
        await service.activate_trial(user.id)
    assert error.value.code == "subscription_exists"


async def test_trial_without_active_plan_is_disabled(db_session: AsyncSession) -> None:
    user = await _user(db_session, "sub00005", 11)
    with pytest.raises(ServiceError) as error:
        await _service(db_session, FakePanel()).activate_trial(user.id)
    assert error.value.code == "trial_disabled"


async def test_trial_gives_link_and_writes_event(db_session: AsyncSession) -> None:
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00006", 12)

    view = await _service(db_session, FakePanel()).activate_trial(user.id)

    assert view.status is SubscriptionState.trial
    assert view.subscription_url is not None

    events = (await db_session.execute(select(SubscriptionEvent))).scalars().all()
    assert [(event.type, event.days_delta) for event in events] == [
        (SubscriptionEventType.trial, 3)
    ]


async def test_panel_gets_access_open_on_first_provision(db_session: AsyncSession) -> None:
    """Панель должна увидеть ACTIVE сразу.

    Примирение читает статус подписки, и при pending_provision закрыло бы
    доступ, который мы как раз выдаём: человек получил бы ссылку, ведущую в
    заблокированный аккаунт, до ближайшего разбора очереди.
    """
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00007", 18)
    panel = FakePanel()

    await _service(db_session, panel).activate_trial(user.id)

    assert [created["status"] for created in panel.users.values()] == ["ACTIVE"]


async def test_dead_panel_leaves_pending_and_queued_task(db_session: AsyncSession) -> None:
    """Панель лежит — дни всё равно начислены, выдача уходит в очередь."""
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00008", 13)
    panel = FakePanel()
    panel.fail_next(times=10)

    view = await _service(db_session, panel).activate_trial(user.id)

    assert view.status is SubscriptionState.pending_provision
    assert view.subscription_url is None
    queued = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert [message.topic for message in queued] == [TOPIC_PROVISION]
    assert [message.processed_at for message in queued] == [None]


async def test_successful_provision_closes_queued_task(db_session: AsyncSession) -> None:
    """Панель уже приведена к нашему состоянию — повторять выдачу незачем."""
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    user = await _user(db_session, "sub00009", 19)

    await _service(db_session, FakePanel()).activate_trial(user.id)

    queued = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert [message.processed_at is not None for message in queued] == [True]


async def test_grant_days_extends_from_expiry(db_session: AsyncSession) -> None:
    plan = await _plan(db_session, "month")
    user = await _user(db_session, "sub00010", 14)
    service = _service(db_session, FakePanel())

    first = await service.grant_days(
        user.id,
        plan,
        30,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.purchase,
        actor=SubscriptionActor.system,
    )
    second = await service.grant_days(
        user.id,
        plan,
        30,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.renew,
        actor=SubscriptionActor.system,
    )

    assert (second.expires_at - first.expires_at) == timedelta(days=30)


async def test_change_plan_converts_remainder(db_session: AsyncSession) -> None:
    cheap = await _plan(db_session, "cheap", price_rub=Decimal("300.00"))
    pricey = await _plan(db_session, "pricey", price_rub=Decimal("600.00"))
    user = await _user(db_session, "sub00011", 15)
    service = _service(db_session, FakePanel())
    await service.grant_days(
        user.id,
        cheap,
        30,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.purchase,
        actor=SubscriptionActor.system,
    )

    changed = await service.change_plan(
        user.id, pricey.id, actor=SubscriptionActor.admin, actor_user_id=user.id
    )

    # 30 дней по 10 ₽/день — это 300 ₽, то есть 15 дней по 20 ₽/день. Доля
    # секунды на выдачу уже прошла, а дробный день домен отбрасывает целиком,
    # поэтому остаётся ровно 14 дней, а не 15.
    remaining = changed.expires_at - datetime.now(UTC)
    assert timedelta(days=13) < remaining <= timedelta(days=14)
    assert changed.plan_code == "pricey"


async def test_change_plan_from_trial_gives_no_days(db_session: AsyncSession) -> None:
    """Стоимость дня триала — ноль: конвертировать нечего, и дни не дарятся."""
    await _plan(db_session, "trial", is_trial=True, duration_days=3, price_rub=Decimal("0.00"))
    paid = await _plan(db_session, "month")
    user = await _user(db_session, "sub00012", 17)
    service = _service(db_session, FakePanel())
    await service.activate_trial(user.id)

    changed = await service.change_plan(
        user.id, paid.id, actor=SubscriptionActor.admin, actor_user_id=user.id
    )

    assert changed.plan_code == "month"
    # Остаток триала не переезжает, а срок нового тарифа не дарится: подписка
    # остаётся без оплаченного времени, и панель закрывает доступ.
    assert changed.status is SubscriptionState.expired


async def test_expire_due_marks_and_disables(db_session: AsyncSession) -> None:
    plan = await _plan(db_session, "month")
    user = await _user(db_session, "sub00013", 16)
    panel = FakePanel()
    service = _service(db_session, panel)
    await service.grant_days(
        user.id,
        plan,
        1,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.purchase,
        actor=SubscriptionActor.system,
    )

    count = await service.expire_due(now=datetime.now(UTC) + timedelta(days=2))

    assert count == 1
    view = await service.current(user.id)
    assert view is not None
    assert view.status is SubscriptionState.expired
