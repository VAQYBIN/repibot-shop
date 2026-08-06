"""Тарифы через админское API."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"

PLAN_BODY: dict[str, Any] = {
    "code": "month",
    "name": {"ru": "Месяц", "en": "Month"},
    "description": None,
    "duration_days": 30,
    "price_rub": "299.00",
    "price_stars": 199,
    "traffic_limit_bytes": 0,
    "traffic_reset_strategy": "NO_RESET",
    "hwid_device_limit": 3,
    "internal_squad_uuids": [SQUAD],
    "is_trial": False,
    "is_visible": True,
    "sort_order": 0,
}


async def test_support_cannot_touch_plans(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Роль support к тарифам доступа не имеет — это правило архитектуры."""
    # Роль проверяется явно: без этого тест проходил бы и с обычным
    # пользователем, то есть проверял бы не то ограничение.
    whoami = await api_client.get("/api/admin/whoami", headers=support_headers)
    assert whoami.json()["role"] == "support"

    response = await api_client.get("/api/admin/plans", headers=support_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_admin_creates_and_archives_plan(
    api_client: AsyncClient, admin_headers: dict[str, str], fake_panel_squad: None
) -> None:
    created = await api_client.post("/api/admin/plans", json=PLAN_BODY, headers=admin_headers)
    assert created.status_code == 201
    plan_id = created.json()["id"]

    listed = await api_client.get("/api/admin/plans", headers=admin_headers)
    assert [plan["code"] for plan in listed.json()] == ["month"]

    archived = await api_client.delete(f"/api/admin/plans/{plan_id}", headers=admin_headers)
    assert archived.status_code == 204

    # Витрина /api/plans появляется только в задаче 12, поэтому здесь
    # проверяется само правило: строка осталась, но снята с продажи.
    after = await api_client.get("/api/admin/plans", headers=admin_headers)
    assert [plan["is_active"] for plan in after.json()] == [False]


async def test_admin_updates_plan(
    api_client: AsyncClient, admin_headers: dict[str, str], fake_panel_squad: None
) -> None:
    created = await api_client.post("/api/admin/plans", json=PLAN_BODY, headers=admin_headers)
    plan_id = created.json()["id"]

    updated = await api_client.patch(
        f"/api/admin/plans/{plan_id}",
        json={**PLAN_BODY, "price_stars": 249},
        headers=admin_headers,
    )

    assert updated.status_code == 200
    assert updated.json()["price_stars"] == 249


async def test_unknown_squad_is_rejected(
    api_client: AsyncClient, admin_headers: dict[str, str], fake_panel: object
) -> None:
    """Панель без сквадов: тариф с несуществующим сквадом не даст доступа."""
    response = await api_client.post("/api/admin/plans", json=PLAN_BODY, headers=admin_headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "plan_squads_unknown"


async def test_squads_come_from_panel(
    api_client: AsyncClient, admin_headers: dict[str, str], fake_panel_squad: None
) -> None:
    response = await api_client.get("/api/admin/remnawave/squads", headers=admin_headers)
    assert response.json() == [{"uuid": SQUAD, "name": "Европа"}]
