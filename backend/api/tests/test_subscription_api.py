"""Витрина и подписка глазами клиента."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import Subscription, SubscriptionSource, User
from repibot_core.domain.subscriptions import SubscriptionState

pytestmark = pytest.mark.docker


async def test_plans_are_public(api_client: AsyncClient, month_plan: int) -> None:
    """Витрина видна до входа: иначе не на что смотреть до регистрации."""
    response = await api_client.get("/api/plans")
    assert response.status_code == 200
    assert [plan["code"] for plan in response.json()] == ["month"]


async def test_showcase_hides_internal_squads(api_client: AsyncClient, month_plan: int) -> None:
    """Состав локаций — наша кухня, клиенту он в ответе не нужен."""
    response = await api_client.get("/api/plans")
    assert "internal_squad_uuids" not in response.json()[0]


async def test_subscription_is_null_for_newcomer(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_plan: int
) -> None:
    """Отсутствие подписки — не ошибка. Иначе фронтенд не отличит её от отказа."""
    response = await api_client.get("/api/me/subscription", headers=telegram_user_headers)
    assert response.status_code == 200
    assert response.json() == {"subscription": None, "trial_available": True}


async def test_trial_is_unavailable_without_telegram(
    api_client: AsyncClient, user_headers: dict[str, str], trial_plan: int
) -> None:
    """Витрина не должна предлагать кнопку, которая заведомо ответит отказом."""
    response = await api_client.get("/api/me/subscription", headers=user_headers)
    assert response.status_code == 200
    assert response.json() == {"subscription": None, "trial_available": False}


async def test_trial_activation_returns_link(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_plan: int
) -> None:
    response = await api_client.post("/api/me/subscription/trial", headers=telegram_user_headers)
    assert response.status_code == 201
    body = response.json()["subscription"]
    assert body["status"] == "trial"
    assert body["subscription_url"].startswith("https://")


async def test_second_trial_is_conflict(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_plan: int
) -> None:
    await api_client.post("/api/me/subscription/trial", headers=telegram_user_headers)
    response = await api_client.post("/api/me/subscription/trial", headers=telegram_user_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "subscription_exists"


async def test_trial_without_telegram_is_conflict(
    api_client: AsyncClient, user_headers: dict[str, str], trial_plan: int
) -> None:
    response = await api_client.post("/api/me/subscription/trial", headers=user_headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "trial_requires_telegram"


async def test_anonymous_cannot_activate_trial(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/me/subscription/trial")
    assert response.status_code == 401


async def test_anonymous_cannot_read_subscription(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/me/subscription")
    assert response.status_code == 401


async def test_auto_renew_reads_and_updates_only_current_subscription(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    plain_user_id: int,
    month_plan: int,
    engine: AsyncEngine,
) -> None:
    """Идентификатор из запроса дал бы одному подписчику менять чужие списания."""
    async with create_session_factory(engine)() as session:
        starts_at = datetime.now(UTC)
        session.add(
            Subscription(
                user_id=plain_user_id,
                plan_id=month_plan,
                status=SubscriptionState.active,
                started_at=starts_at,
                expires_at=starts_at + timedelta(days=30),
                auto_renew_enabled=False,
                source=SubscriptionSource.purchase,
            )
        )
        other = User(email="other-renew@example.org", referral_code="renewoth")
        session.add(other)
        await session.flush()
        session.add(
            Subscription(
                user_id=other.id,
                plan_id=month_plan,
                status=SubscriptionState.active,
                started_at=starts_at,
                expires_at=starts_at + timedelta(days=30),
                auto_renew_enabled=False,
                source=SubscriptionSource.purchase,
            )
        )
        await session.commit()

    before = await api_client.get("/api/me/subscription/auto-renew", headers=user_headers)
    changed = await api_client.put(
        "/api/me/subscription/auto-renew",
        headers=user_headers,
        json={"auto_renew_enabled": True},
    )

    assert before.status_code == 200
    assert before.json() == {"auto_renew_enabled": False}
    assert changed.status_code == 200
    assert changed.json() == {"auto_renew_enabled": True}
    subscription = (await api_client.get("/api/me/subscription", headers=user_headers)).json()[
        "subscription"
    ]
    assert subscription["auto_renew_enabled"] is True
    async with create_session_factory(engine)() as session:
        other_enabled = await session.scalar(
            select(Subscription.auto_renew_enabled).where(Subscription.user_id == other.id)
        )
    assert other_enabled is False


async def test_auto_renew_without_subscription_has_stable_error(
    api_client: AsyncClient, user_headers: dict[str, str]
) -> None:
    response = await api_client.put(
        "/api/me/subscription/auto-renew",
        headers=user_headers,
        json={"auto_renew_enabled": True},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "subscription_not_found"


async def test_auto_renew_rejects_trial_subscription(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_plan: int
) -> None:
    activated = await api_client.post("/api/me/subscription/trial", headers=telegram_user_headers)
    assert activated.status_code == 201

    response = await api_client.put(
        "/api/me/subscription/auto-renew",
        headers=telegram_user_headers,
        json={"auto_renew_enabled": True},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "auto_renew_unavailable"
