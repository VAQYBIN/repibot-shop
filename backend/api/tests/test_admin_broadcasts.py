"""Админские маршруты рассылок: гейт роли, охват, запуск и отмена."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import AuditLog, BroadcastRecipient

pytestmark = pytest.mark.docker

CAMPAIGN = {
    "segment": "all",
    "title": {"ru": "Скидка", "en": "Sale"},
    "body": {"ru": "Три дня в подарок", "en": "Three days for free"},
}


async def _create(client: AsyncClient, headers: dict[str, str]) -> int:
    created = await client.post("/api/admin/broadcasts", json=CAMPAIGN, headers=headers)
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


async def test_support_role_cannot_touch_broadcasts(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Роль поддержки не имеет доступа к рассылкам — так решено архитектурой."""
    listing = await api_client.get("/api/admin/broadcasts", headers=support_headers)
    creating = await api_client.post(
        "/api/admin/broadcasts", json=CAMPAIGN, headers=support_headers
    )
    reach = await api_client.get("/api/admin/segments/all/count", headers=support_headers)

    assert listing.status_code == 403
    assert creating.status_code == 403
    assert reach.status_code == 403


async def test_admin_sees_reach_before_launching(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Охват до запуска — единственная защита от «отправил не тем»."""
    response = await api_client.get("/api/admin/segments/all/count", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["count"] >= 1


async def test_unknown_segment_is_refused_instead_of_crashing(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """`segment_query` бросает KeyError: непойманный, он стал бы 500 на опечатке."""
    response = await api_client.get("/api/admin/segments/nonesuch/count", headers=admin_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_segment"


async def test_campaign_without_russian_text_is_refused(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Русский текст запасной при отправке: без него часть аудитории получит пустоту."""
    response = await api_client.post(
        "/api/admin/broadcasts",
        json={"segment": "all", "title": {"en": "Sale"}, "body": {"en": "Free days"}},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "broadcast_text_required"


async def test_draft_becomes_running_with_a_fixed_audience(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    engine: AsyncEngine,
) -> None:
    """Запуск фиксирует аудиторию и пишет обе операции в журнал."""
    broadcast_id = await _create(api_client, admin_headers)

    listing = await api_client.get("/api/admin/broadcasts", headers=admin_headers)
    started = await api_client.post(
        f"/api/admin/broadcasts/{broadcast_id}/start", headers=admin_headers
    )
    single = await api_client.get(f"/api/admin/broadcasts/{broadcast_id}", headers=admin_headers)

    assert [item["status"] for item in listing.json()] == ["draft"]
    assert started.status_code == 200
    assert started.json()["planned_count"] >= 1
    assert single.json()["status"] == "running"
    assert single.json()["started_at"] is not None
    async with create_session_factory(engine)() as session:
        recipients = list(
            (
                await session.scalars(
                    select(BroadcastRecipient).where(
                        BroadcastRecipient.broadcast_id == broadcast_id
                    )
                )
            ).all()
        )
        actions = list(
            (
                await session.scalars(
                    select(AuditLog.action)
                    .where(AuditLog.entity == "broadcast")
                    .order_by(AuditLog.id)
                )
            ).all()
        )
    assert len(recipients) == started.json()["planned_count"]
    assert actions == ["broadcast.create", "broadcast.start"]


async def test_second_campaign_waits_for_the_running_one(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    """Две одновременные поделили бы лимит Telegram и шли бы вдвое дольше."""
    first = await _create(api_client, admin_headers)
    second = await _create(api_client, admin_headers)

    await api_client.post(f"/api/admin/broadcasts/{first}/start", headers=admin_headers)
    response = await api_client.post(f"/api/admin/broadcasts/{second}/start", headers=admin_headers)
    repeated = await api_client.post(f"/api/admin/broadcasts/{first}/start", headers=admin_headers)

    assert (response.status_code, response.json()["error"]["code"]) == (409, "broadcast_busy")
    assert (repeated.status_code, repeated.json()["error"]["code"]) == (409, "broadcast_not_draft")


async def test_cancel_stops_a_running_campaign_and_refuses_a_draft(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    engine: AsyncEngine,
) -> None:
    """Отмена обязана быть доступна из админки: остановить рассылку иначе нечем."""
    broadcast_id = await _create(api_client, admin_headers)
    draft = await _create(api_client, admin_headers)
    await api_client.post(f"/api/admin/broadcasts/{broadcast_id}/start", headers=admin_headers)

    canceled = await api_client.post(
        f"/api/admin/broadcasts/{broadcast_id}/cancel", headers=admin_headers
    )
    refused = await api_client.post(f"/api/admin/broadcasts/{draft}/cancel", headers=admin_headers)

    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    assert canceled.json()["finished_at"] is not None
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "broadcast_not_running")
    async with create_session_factory(engine)() as session:
        actions = list(
            (
                await session.scalars(
                    select(AuditLog.action)
                    .where(AuditLog.entity == "broadcast", AuditLog.entity_id == str(broadcast_id))
                    .order_by(AuditLog.id)
                )
            ).all()
        )
    assert actions == ["broadcast.create", "broadcast.start", "broadcast.cancel"]


async def test_missing_campaign_is_a_404(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Номер из чужой вкладки не должен приводить к 500."""
    single = await api_client.get("/api/admin/broadcasts/999999", headers=admin_headers)
    started = await api_client.post("/api/admin/broadcasts/999999/start", headers=admin_headers)

    assert single.status_code == 404
    assert started.status_code == 404
