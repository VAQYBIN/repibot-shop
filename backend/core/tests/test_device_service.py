"""Устройства: кэш, лимит тарифа, чужой hwid."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.services.devices import DeviceService
from repibot_core.services.errors import ServiceError
from repibot_core.services.panel_cache import PanelCache
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _subscriber(db_session: AsyncSession, *, panel_id: int, device_limit: int) -> User:
    plan = await PlanRepository(db_session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=device_limit,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="d@example.org", referral_code="dev00001", remnawave_id=panel_id)
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await db_session.commit()
    return user


def _service(db_session: AsyncSession, panel: FakePanel) -> DeviceService:
    return DeviceService(
        db_session, PanelDevices(panel.client()), PanelCache(FakeRedis(), ttl_seconds=60)
    )


async def test_list_reports_limit_from_plan(db_session: AsyncSession) -> None:
    user = await _subscriber(db_session, panel_id=7, device_limit=3)
    panel = FakePanel()
    panel.add_device(7, "hwid-1", platform="iOS")

    view = await _service(db_session, panel).list(user.id)

    assert view.limit == 3
    assert view.used == 1
    assert view.devices[0].platform == "iOS"


async def test_second_call_does_not_hit_panel(db_session: AsyncSession) -> None:
    """Список устройств меняется редко, а экран кабинета опрашивают часто."""
    user = await _subscriber(db_session, panel_id=7, device_limit=3)
    panel = FakePanel()
    panel.add_device(7, "hwid-1")
    service = _service(db_session, panel)
    await service.list(user.id)

    panel.requests.clear()
    await service.list(user.id)

    assert panel.requests == []


async def test_unlink_drops_cache_immediately(db_session: AsyncSession) -> None:
    """Иначе человек жмёт «отвязать» и минуту видит удалённое устройство."""
    user = await _subscriber(db_session, panel_id=7, device_limit=3)
    panel = FakePanel()
    panel.add_device(7, "hwid-1")
    service = _service(db_session, panel)
    await service.list(user.id)

    await service.unlink(user.id, "hwid-1")

    assert (await service.list(user.id)).used == 0


async def test_unlink_of_foreign_device_is_refused(db_session: AsyncSession) -> None:
    """Проверка по ответу панели, а не по факту, что клиент прислал знакомый hwid."""
    user = await _subscriber(db_session, panel_id=7, device_limit=3)
    panel = FakePanel()
    panel.add_device(9, "чужое")

    with pytest.raises(ServiceError) as error:
        await _service(db_session, panel).unlink(user.id, "чужое")
    assert error.value.code == "device_not_found"


async def test_user_without_subscription_gets_service_error(db_session: AsyncSession) -> None:
    user = User(email="n@example.org", referral_code="dev00002")
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(ServiceError) as error:
        await _service(db_session, FakePanel()).list(user.id)
    assert error.value.code == "subscription_missing"
