"""Крон истечения снимает доступ у просроченных подписок."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.settings import get_settings
from repibot_core.tasks import expire_subscriptions


def test_task_is_scheduled_hourly() -> None:
    """Раз в час, а не раз в сутки: сутки лишнего доступа — это деньги."""
    assert expire_subscriptions.labels["schedule"] == [{"cron": "0 * * * *"}]


@pytest.mark.docker
async def test_task_expires_overdue_subscription(
    postgres_url: str, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Задача ходит в базу сама, поэтому ей подменяется адрес подключения."""
    plan = await PlanRepository(db_session).create(
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
    user = User(email="exp@example.org", referral_code="exp00001")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now - timedelta(days=31),
        expires_at=now - timedelta(hours=1),
        source=SubscriptionSource.purchase,
    )
    # Коммит обязателен: задача открывает своё подключение и незакоммиченную
    # строку тестовой транзакции просто не увидит.
    await db_session.commit()

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", postgres_url)

    assert await expire_subscriptions() == {"expired": 1}

    subscription = await SubscriptionRepository(db_session).get_for_user(user.id)
    assert subscription is not None
    # Задача правила строку из своей сессии, а тестовая помнит прежнюю копию в
    # карте идентичности. Без refresh проверялся бы устаревший статус.
    await db_session.refresh(subscription)
    assert subscription.status is SubscriptionState.expired
