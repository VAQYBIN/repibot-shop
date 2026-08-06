"""Витрина и подписка глазами клиента."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

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
