"""Примирение панели с нашим состоянием."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.client import RemnawaveUnavailable
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.provisioning import ProvisioningService
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _prepare(session: AsyncSession) -> User:
    plan = await PlanRepository(session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=1024,
        traffic_reset_strategy=TrafficResetStrategy.MONTH,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="p@example.org", referral_code="prov0001", telegram_id=99)
    session.add(user)
    await session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.pending_provision,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await session.commit()
    return user


def _service(session: AsyncSession, panel: FakePanel) -> ProvisioningService:
    return ProvisioningService(session, PanelUsers(panel.client()))


async def test_creates_user_with_our_name_and_tag(db_session: AsyncSession) -> None:
    user = await _prepare(db_session)
    panel = FakePanel()

    state = await _service(db_session, panel).reconcile(user.id)

    created = panel.users[state.panel_id]
    assert created["username"] == f"rp_{user.id}"
    assert created["tag"] == "REPIBOT"
    assert created["telegramId"] == 99
    assert created["hwidDeviceLimit"] == 3
    assert [squad["uuid"] for squad in created["activeInternalSquads"]] == [SQUAD]


async def test_saves_panel_id_and_short_uuid(db_session: AsyncSession) -> None:
    user = await _prepare(db_session)
    panel = FakePanel()

    state = await _service(db_session, panel).reconcile(user.id)
    await db_session.refresh(user)

    assert user.remnawave_id == state.panel_id
    assert user.remnawave_short_uuid == state.short_uuid


async def test_second_run_sends_no_writes(db_session: AsyncSession) -> None:
    """Идемпотентность: на сошедшихся данных изменяющих запросов нет."""
    user = await _prepare(db_session)
    panel = FakePanel()
    service = _service(db_session, panel)
    await service.reconcile(user.id)

    panel.requests.clear()
    await service.reconcile(user.id)

    assert [method for method, _ in panel.requests] == ["GET"]


async def test_millisecond_precision_in_panel_is_not_a_difference(
    db_session: AsyncSession,
) -> None:
    """Живая панель хранит дату с миллисекундами, а мы — с микросекундами.

    Заглушка возвращает ровно ту строку, что получила, поэтому сама по себе
    расхождение не воспроизводит. Округление здесь повторяет поведение панели:
    без сравнения до секунды реконсиляция писала бы PATCH на каждом прогоне.
    """
    user = await _prepare(db_session)
    panel = FakePanel()
    service = _service(db_session, panel)
    state = await service.reconcile(user.id)

    stored = panel.users[state.panel_id]
    expire_at = datetime.fromisoformat(str(stored["expireAt"]))
    stored["expireAt"] = expire_at.replace(
        microsecond=expire_at.microsecond // 1000 * 1000
    ).isoformat()

    panel.requests.clear()
    await service.reconcile(user.id)

    assert [method for method, _ in panel.requests] == ["GET"]


async def test_lost_panel_id_is_recovered_by_username(db_session: AsyncSession) -> None:
    """Пользователь не дублируется, если мы потеряли числовой идентификатор."""
    user = await _prepare(db_session)
    panel = FakePanel()
    service = _service(db_session, panel)
    first = await service.reconcile(user.id)

    user.remnawave_id = None
    await db_session.commit()

    second = await service.reconcile(user.id)

    assert second.panel_id == first.panel_id
    assert len(panel.users) == 1


async def test_expired_subscription_disables_panel_user(db_session: AsyncSession) -> None:
    user = await _prepare(db_session)
    panel = FakePanel()
    service = _service(db_session, panel)
    state = await service.reconcile(user.id)

    subscription = await SubscriptionRepository(db_session).get_for_user(user.id)
    assert subscription is not None
    subscription.status = SubscriptionState.expired
    await db_session.commit()

    await service.reconcile(user.id)
    assert panel.users[state.panel_id]["status"] == "DISABLED"


async def test_unavailable_panel_raises(db_session: AsyncSession) -> None:
    user = await _prepare(db_session)
    panel = FakePanel()
    panel.fail_next(times=10)

    with pytest.raises(RemnawaveUnavailable):
        await _service(db_session, panel).reconcile(user.id)


async def test_paid_subscription_becomes_provisioned_when_the_panel_answers(
    db_session: AsyncSession,
) -> None:
    """Финализация оплаты оставляет подписку невыданной: доступ открывает выдача.

    reconcile читает наш статус, чтобы решить, открывать доступ или закрывать,
    и на невыданной подписке завёл бы в панели отключённого пользователя.
    Оплаченный доступ не появился бы никогда.
    """
    user = await _prepare(db_session)
    panel = FakePanel()

    state = await _service(db_session, panel).provision(user.id)

    assert panel.users[state.panel_id]["status"] == "ACTIVE"
    subscription = await SubscriptionRepository(db_session).get_for_user(user.id)
    assert subscription is not None
    assert subscription.status is SubscriptionState.active


async def test_unanswering_panel_leaves_the_subscription_unprovisioned(
    db_session: AsyncSession,
) -> None:
    """Отказ панели возвращает подписку в невыданную, и очередь повторит выдачу.

    Оставить её выданной значило бы показать человеку рабочую подписку,
    которой в панели нет.
    """
    user = await _prepare(db_session)
    panel = FakePanel()
    panel.fail_next(times=10)

    with pytest.raises(RemnawaveUnavailable):
        await _service(db_session, panel).provision(user.id)

    subscription = await SubscriptionRepository(db_session).get_for_user(user.id)
    assert subscription is not None
    assert subscription.status is SubscriptionState.pending_provision
