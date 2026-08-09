"""Начисление дней и смена тарифа руками админа."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import AuditLog

pytestmark = pytest.mark.docker


async def test_admin_grants_days(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    fake_panel_squad: None,
) -> None:
    response = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 10, "comment": "компенсация"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["subscription"]["plan_code"] == "month"


async def test_grant_is_written_to_audit_log(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    fake_panel_squad: None,
    engine: AsyncEngine,
) -> None:
    """Каждое действие персонала оставляет след — это правило архитектуры."""
    await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 10},
        headers=admin_headers,
    )

    # Своя сессия, а не фикстура db_session: она пересоздаёт схему и стёрла бы
    # пользователя с тарифом, заведённых фикстурами выше.
    # Отбор по сущности: в журнале уже лежит выдача роли администратора,
    # случившаяся при его входе.
    async with create_session_factory(engine)() as session:
        records = list(
            (
                await session.execute(select(AuditLog).where(AuditLog.entity == "subscription"))
            ).scalars()
        )

    assert [record.action for record in records] == ["subscription.grant"]
    assert records[0].actor_id != plain_user_id
    # Подписки до начисления не было, и в журнале это видно.
    assert records[0].before is None
    assert records[0].after is not None
    assert records[0].after["plan_code"] == "month"


async def test_support_cannot_grant(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
) -> None:
    response = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 10},
        headers=support_headers,
    )
    assert response.status_code == 403


async def test_unknown_plan_is_not_found(
    api_client: AsyncClient, admin_headers: dict[str, str], plain_user_id: int
) -> None:
    response = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": 404, "days": 10},
        headers=admin_headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "plan_not_found"


async def test_plan_change_keeps_paid_remainder(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    fake_panel_squad: None,
) -> None:
    """Тело без days — смена тарифа: остаток переезжает, а не начисляется заново."""
    granted = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 30},
        headers=admin_headers,
    )
    expires_at = granted.json()["subscription"]["expires_at"]

    changed = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan},
        headers=admin_headers,
    )

    assert changed.status_code == 200
    # Тариф тот же, цена дня та же — значит и срок остаётся прежним с точностью
    # до отброшенного дробного дня.
    assert changed.json()["subscription"]["expires_at"] <= expires_at
