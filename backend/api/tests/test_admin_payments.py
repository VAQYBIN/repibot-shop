"""Админская отметка возврата и явные компенсации."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import (
    AuditLog,
    Order,
    OrderStatus,
    Plan,
    ReferralReward,
    Subscription,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionSource,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.provisioning import build_provision_handler
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker


async def _fulfilled_order(
    engine: AsyncEngine, *, user_id: int, plan_id: int, key: str = "admin-refund-order"
) -> Order:
    async with create_session_factory(engine)() as session:
        plan = await session.get(Plan, plan_id)
        assert plan is not None
        order = await OrderRepository(session).create_pending(
            user_id=user_id,
            plan=plan,
            client_key=key,
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        order.status = OrderStatus.fulfilled
        await session.commit()
        return order


async def test_refund_mark_never_revokes_days_implicitly(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
    fake_panel_squad: None,
) -> None:
    granted = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 10, "comment": "paid term"},
        headers=admin_headers,
    )
    assert granted.status_code == 200
    order = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)
    async with create_session_factory(engine)() as session:
        before = await session.scalar(
            select(Subscription).where(Subscription.user_id == plain_user_id)
        )
    assert before is not None
    expires_before = before.expires_at

    response = await api_client.post(
        f"/api/admin/orders/{order.id}/refund-mark",
        json={"reference": "rf_1", "comment": "YooKassa refund completed"},
        headers=admin_headers,
    )

    assert response.status_code == 204
    async with create_session_factory(engine)() as session:
        stored = await session.get(Order, order.id)
        assert stored is not None and stored.status is OrderStatus.refunded
        subscription = await session.scalar(
            select(Subscription).where(Subscription.user_id == plain_user_id)
        )
        audit = await session.scalar(select(AuditLog).where(AuditLog.action == "order.refund_mark"))
    assert subscription is not None
    assert subscription.expires_at == expires_before
    assert audit is not None
    assert audit.after is not None
    assert audit.after["status"] == "refunded"
    assert audit.after["reference"] == "rf_1"
    assert audit.after["comment"] == "YooKassa refund completed"


async def test_refund_mark_requires_provider_reference_and_comment(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
) -> None:
    order = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)

    response = await api_client.post(
        f"/api/admin/orders/{order.id}/refund-mark",
        json={"reference": "", "comment": ""},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_payment_admin_routes_reject_support(
    api_client: AsyncClient,
    support_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
) -> None:
    order = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)

    response = await api_client.post(
        f"/api/admin/orders/{order.id}/refund-mark",
        json={"reference": "rf_1", "comment": "YooKassa refund completed"},
        headers=support_headers,
    )

    assert response.status_code == 403


async def test_admin_assertion_cookie_never_authorizes_payment_mutations(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
) -> None:
    """Cookie для показа админки игнорируется, даже если её подсунуть в запрос API."""
    order = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)

    response = await api_client.post(
        f"/api/admin/orders/{order.id}/refund-mark",
        json={"reference": "rf_cookie", "comment": "must still require backend admin"},
        headers={
            **user_headers,
            "Cookie": "repibot_admin_assertion=not-an-api-credential",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_revoke_days_compensation_is_audited_and_idempotent(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
    fake_panel_squad: None,
) -> None:
    granted = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 30, "comment": "paid term"},
        headers=admin_headers,
    )
    assert granted.status_code == 200
    order = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)
    payload = {
        "action": "revoke_days",
        "idempotency_key": "refund-rf_1-revoke",
        "comment": "separate approved compensation",
    }

    first = await api_client.post(
        f"/api/admin/orders/{order.id}/compensations", json=payload, headers=admin_headers
    )
    retry = await api_client.post(
        f"/api/admin/orders/{order.id}/compensations", json=payload, headers=admin_headers
    )
    second_action = await api_client.post(
        f"/api/admin/orders/{order.id}/compensations",
        json={**payload, "idempotency_key": "refund-rf_1-revoke-again"},
        headers=admin_headers,
    )

    assert first.status_code == 204
    assert retry.status_code == 204
    assert second_action.status_code == 409
    assert second_action.json()["error"]["code"] == "compensation_already_applied"
    async with create_session_factory(engine)() as session:
        events = list(
            (
                await session.scalars(
                    select(SubscriptionEvent).where(
                        SubscriptionEvent.type == SubscriptionEventType.admin_revoke
                    )
                )
            ).all()
        )
        audits = list(
            (
                await session.scalars(
                    select(AuditLog).where(AuditLog.action == "order.compensation")
                )
            ).all()
        )
    assert len(events) == 1
    assert events[0].days_delta == -30
    assert len(audits) == 1


async def test_partial_revoke_keeps_remaining_access_active_in_panel(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
    fake_panel_squad: None,
    fake_panel: FakePanel,
) -> None:
    granted = await api_client.post(
        f"/api/admin/users/{plain_user_id}/subscription",
        json={"plan_id": month_plan, "days": 60, "comment": "paid term"},
        headers=admin_headers,
    )
    assert granted.status_code == 200
    order = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)

    response = await api_client.post(
        f"/api/admin/orders/{order.id}/compensations",
        json={
            "action": "revoke_days",
            "idempotency_key": "partial-revoke",
            "comment": "separate approved compensation",
        },
        headers=admin_headers,
    )

    assert response.status_code == 204
    async with create_session_factory(engine)() as session:
        subscription = await session.scalar(
            select(Subscription).where(Subscription.user_id == plain_user_id)
        )
    assert subscription is not None
    assert subscription.status is SubscriptionState.active
    assert subscription.expires_at > datetime.now(UTC)

    await build_provision_handler(create_session_factory(engine), PanelUsers(fake_panel.client()))(
        {"user_id": plain_user_id}
    )
    assert [user["status"] for user in fake_panel.users.values()] == ["ACTIVE"]


async def test_reverse_referral_reward_is_separate_one_time_compensation(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
) -> None:
    order = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)
    async with create_session_factory(engine)() as session:
        referrer = User(email="referrer@example.org", referral_code="adminref")
        session.add(referrer)
        await session.flush()
        subscription = Subscription(
            user_id=referrer.id,
            plan_id=month_plan,
            status=SubscriptionState.active,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=40),
            source=SubscriptionSource.purchase,
            entitlement_price_rub=0,
            entitlement_duration_days=30,
        )
        session.add(subscription)
        session.add(
            ReferralReward(
                referrer_user_id=referrer.id,
                referee_user_id=plain_user_id,
                origin_order_id=order.id,
                days=3,
            )
        )
        await session.commit()

    payload = {
        "action": "reverse_referral_reward",
        "idempotency_key": "reverse-referral-rf_1",
        "comment": "separate approved compensation",
    }
    first = await api_client.post(
        f"/api/admin/orders/{order.id}/compensations", json=payload, headers=admin_headers
    )
    retry = await api_client.post(
        f"/api/admin/orders/{order.id}/compensations", json=payload, headers=admin_headers
    )

    assert (first.status_code, retry.status_code) == (204, 204)
    async with create_session_factory(engine)() as session:
        reward = await session.scalar(
            select(ReferralReward).where(ReferralReward.origin_order_id == order.id)
        )
    assert reward is not None and reward.reversed_at is not None


async def test_payment_admin_state_errors_are_stable_4xx(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
) -> None:
    pending = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)
    async with create_session_factory(engine)() as session:
        stored = await session.get(Order, pending.id)
        assert stored is not None
        stored.status = OrderStatus.pending
        await session.commit()

    invalid_refund = await api_client.post(
        f"/api/admin/orders/{pending.id}/refund-mark",
        json={"reference": "rf_1", "comment": "YooKassa refund completed"},
        headers=admin_headers,
    )
    missing_order = await api_client.post(
        "/api/admin/orders/999999/compensations",
        json={
            "action": "revoke_days",
            "idempotency_key": "missing-order",
            "comment": "separate approved compensation",
        },
        headers=admin_headers,
    )
    fulfilled = await _fulfilled_order(
        engine, user_id=plain_user_id, plan_id=month_plan, key="missing-reward-order"
    )
    missing_reward = await api_client.post(
        f"/api/admin/orders/{fulfilled.id}/compensations",
        json={
            "action": "reverse_referral_reward",
            "idempotency_key": "missing-reward",
            "comment": "separate approved compensation",
        },
        headers=admin_headers,
    )

    assert (invalid_refund.status_code, invalid_refund.json()["error"]["code"]) == (
        409,
        "refund_invalid",
    )
    assert (missing_order.status_code, missing_order.json()["error"]["code"]) == (
        404,
        "order_not_found",
    )
    assert (missing_reward.status_code, missing_reward.json()["error"]["code"]) == (
        404,
        "reward_missing",
    )


async def test_historical_duplicate_compensation_actions_are_a_safe_conflict(
    api_client: AsyncClient,
    admin_headers: dict[str, str],
    month_plan: int,
    plain_user_id: int,
    engine: AsyncEngine,
) -> None:
    order = await _fulfilled_order(engine, user_id=plain_user_id, plan_id=month_plan)
    async with create_session_factory(engine)() as session:
        for key in ("historic-revoke-one", "historic-revoke-two"):
            session.add(
                AuditLog(
                    action="order.compensation",
                    entity="order",
                    entity_id=str(order.id),
                    after={"action": "revoke_days", "idempotency_key": key},
                )
            )
        await session.commit()

    response = await api_client.post(
        f"/api/admin/orders/{order.id}/compensations",
        json={
            "action": "revoke_days",
            "idempotency_key": "new-revoke-key",
            "comment": "separate approved compensation",
        },
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "compensation_already_applied"
    async with create_session_factory(engine)() as session:
        records = list(
            (
                await session.scalars(
                    select(AuditLog).where(
                        AuditLog.action == "order.compensation",
                        AuditLog.entity_id == str(order.id),
                    )
                )
            ).all()
        )
    assert len(records) == 2
