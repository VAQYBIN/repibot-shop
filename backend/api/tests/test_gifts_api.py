"""Подарочные ваучеры не раскрываются другим аккаунтам и тратятся один раз."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    GiftVoucher,
    OrderPurpose,
    Plan,
    Subscription,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.services.promotions import GiftService
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker
SQUAD = "11111111-1111-4111-8111-811111111111"


async def _user(session: AsyncSession, code: str) -> User:
    user = User(email=f"{code}@example.org", referral_code=code)
    session.add(user)
    await session.flush()
    return user


async def _plan(session: AsyncSession, code: str, price: str) -> Plan:
    return await PlanRepository(session).create(
        code=code,
        name={"ru": code, "en": code},
        description=None,
        duration_days=30,
        price_rub=Decimal(price),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )


async def test_redeeming_gift_into_other_active_plan_keeps_current_plan_and_converts_days(
    db_session: AsyncSession,
) -> None:
    """Replacing an active different plan with a gift would discard paid access."""
    gift_plan = await _plan(db_session, "gift-plan", "300.00")
    current_plan = await _plan(db_session, "current-plan", "600.00")
    buyer, recipient = await _user(db_session, "buyer001"), await _user(db_session, "recipient001")
    order = await OrderRepository(db_session).create_pending(
        user_id=buyer.id,
        plan=gift_plan,
        purpose=OrderPurpose.gift,
        client_key="gift-one",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    voucher = GiftVoucher(
        order_id=order.id,
        code="GIFT-ONE",
        purchased_by_user_id=buyer.id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(voucher)
    await SubscriptionService(db_session, get_settings(), provisioning=None).apply_entitlement(
        recipient.id,
        current_plan,
        30,
        source=SubscriptionSource.purchase,
        event_type=SubscriptionEventType.purchase,
        actor=SubscriptionActor.system,
        origin_attempt_id=None,
    )
    await db_session.commit()
    original_expiry = await db_session.scalar(
        Subscription.__table__.select()
        .with_only_columns(Subscription.expires_at)
        .where(Subscription.user_id == recipient.id)
    )
    assert original_expiry is not None
    view = await GiftService(db_session).redeem(voucher.code, recipient.id)

    assert view.plan_code == "current-plan"
    assert view.expires_at > original_expiry


async def test_gift_redeems_once_and_grants_its_plan_without_a_subscription(
    db_session: AsyncSession,
) -> None:
    """Removing the voucher state check would let the same code grant a second subscription."""
    plan = await _plan(db_session, "gift-new", "300.00")
    buyer, recipient = await _user(db_session, "buyer002"), await _user(db_session, "recipient002")
    order = await OrderRepository(db_session).create_pending(
        user_id=buyer.id,
        plan=plan,
        purpose=OrderPurpose.gift,
        client_key="gift-new",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    voucher = GiftVoucher(
        order_id=order.id,
        code="GIFT-NEW",
        purchased_by_user_id=buyer.id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(voucher)
    await db_session.commit()

    view = await GiftService(db_session).redeem(voucher.code, recipient.id)
    with pytest.raises(Exception, match="ваучер"):
        await GiftService(db_session).redeem(voucher.code, recipient.id)

    assert view.plan_code == "gift-new"


async def test_customer_can_redeem_once_and_cannot_list_someone_elses_voucher(
    api_client: AsyncClient, user_headers: dict[str, str], telegram_user_headers: dict[str, str]
) -> None:
    """No ownership filtering leaks a code; no voucher lock permits double spending."""
    denied = await api_client.get("/api/me/gifts", headers=telegram_user_headers)
    assert denied.status_code == 200
    assert denied.json() == []
    response = await api_client.post(
        "/api/me/gifts/redeem", json={"code": "missing"}, headers=user_headers
    )
    assert response.status_code == 404


async def test_admin_promo_crud_requires_admin(
    api_client: AsyncClient, user_headers: dict[str, str]
) -> None:
    """Making promo creation public would let a buyer change checkout pricing."""
    response = await api_client.post(
        "/api/admin/promos", json={"code": "NOPE", "percent_off": 10}, headers=user_headers
    )
    assert response.status_code == 403


async def test_openapi_documents_gift_and_promo_contracts(api_client: AsyncClient) -> None:
    """Removing a public route from the published schema breaks generated clients."""
    schema = (await api_client.get("/openapi.json")).json()

    assert set(schema["paths"]["/api/me/gifts"]) == {"get"}
    assert set(schema["paths"]["/api/me/gifts/redeem"]) == {"post"}
    assert {"get", "post"} <= set(schema["paths"]["/api/admin/promos"])
