"""Трафик: текущий период, разбивка по дням, кэш."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.client import RemnawaveClient
from repibot_core.integrations.remnawave.stats import PanelStats
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError
from repibot_core.services.panel_cache import PanelCache
from repibot_core.services.traffic import TrafficService
from repibot_core.testing.remnawave import BASE_URL, FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"
TODAY = date(2026, 8, 6)


async def _subscriber(db_session: AsyncSession, *, panel_id: int, limit: int) -> User:
    plan = await PlanRepository(db_session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=limit,
        traffic_reset_strategy=TrafficResetStrategy.MONTH,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="t@example.org", referral_code="trf00001", remnawave_id=panel_id)
    db_session.add(user)
    await db_session.flush()

    from datetime import UTC, datetime, timedelta

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


def _service(db_session: AsyncSession, panel: FakePanel) -> TrafficService:
    client = panel.client()
    return TrafficService(
        db_session, PanelUsers(client), PanelStats(client), PanelCache(FakeRedis(), ttl_seconds=60)
    )


async def test_days_are_summed_across_nodes(db_session: AsyncSession) -> None:
    """Человеку нужен трафик за день, а не разбивка по нодам."""
    user = await _subscriber(db_session, panel_id=1, limit=1024)
    panel = FakePanel()
    await _create_panel_user(panel)
    panel.add_usage(1, "2026-08-05", 100)
    panel.add_usage(1, "2026-08-06", 250)

    view = await _service(db_session, panel).current(user.id, days=7, today=TODAY)

    assert [(day.day, day.used_bytes) for day in view.days] == [
        (date(2026, 8, 5), 100),
        (date(2026, 8, 6), 250),
    ]
    assert view.limit_bytes == 1024


async def test_day_adds_up_every_node(db_session: AsyncSession) -> None:
    """Ноды складываются, а готовое sparklineData не берётся.

    Панель-заглушка отдаёт один ряд, и на ней сложение неотличимо от выбора
    первого ряда. Ответ с двумя нодами собирается здесь же: в схеме нигде не
    сказано, что sparklineData — это сумма ряда, поэтому в ответе он намеренно
    неверен, и тест падает, если сервис поверит ему вместо своего счёта.
    """
    user = await _subscriber(db_session, panel_id=1, limit=0)
    panel = FakePanel()
    await _create_panel_user(panel)

    service = TrafficService(
        db_session,
        PanelUsers(panel.client()),
        _two_node_stats(),
        PanelCache(FakeRedis(), ttl_seconds=60),
    )
    view = await service.current(user.id, days=7, today=TODAY)

    assert [(day.day, day.used_bytes) for day in view.days] == [
        (date(2026, 8, 5), 30),
        (date(2026, 8, 6), 700),
    ]


def _two_node_stats() -> PanelStats:
    """Статистика с двумя нодами и заведомо неверным sparklineData."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": {
                    "categories": ["2026-08-05", "2026-08-06"],
                    "sparklineData": [-1, -1],
                    "topNodes": [],
                    "series": [
                        {
                            "uuid": "22222222-2222-4222-8222-222222222222",
                            "name": "Нидерланды",
                            "color": "#000000",
                            "countryCode": "NL",
                            "total": 130,
                            "data": [10, 120],
                        },
                        {
                            "uuid": "33333333-3333-4333-8333-333333333333",
                            "name": "Германия",
                            "color": "#111111",
                            "countryCode": "DE",
                            "total": 600,
                            "data": [20, 580],
                        },
                    ],
                }
            },
        )

    return PanelStats(
        RemnawaveClient(
            base_url=BASE_URL,
            token="test",
            max_attempts=1,
            transport=httpx.MockTransport(handle),
        )
    )


async def test_second_call_does_not_hit_panel(db_session: AsyncSession) -> None:
    user = await _subscriber(db_session, panel_id=1, limit=0)
    panel = FakePanel()
    await _create_panel_user(panel)
    service = _service(db_session, panel)
    await service.current(user.id, today=TODAY)

    panel.requests.clear()
    await service.current(user.id, today=TODAY)

    assert panel.requests == []


async def test_user_without_panel_id_gets_service_error(db_session: AsyncSession) -> None:
    user = User(email="np@example.org", referral_code="trf00002")
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(ServiceError) as error:
        await _service(db_session, FakePanel()).current(user.id, today=TODAY)
    assert error.value.code == "subscription_missing"


async def _create_panel_user(panel: FakePanel) -> None:
    """Пользователь в панели нужен ради userTraffic в его объекте."""
    from datetime import UTC, datetime

    from repibot_core.integrations.remnawave.types import CreateUserBody

    await PanelUsers(panel.client()).create(
        CreateUserBody(username="rp_1", expireAt=datetime(2026, 9, 6, 12, tzinfo=UTC))
    )
