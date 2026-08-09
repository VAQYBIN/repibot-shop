"""Публичный контракт ручных заказов: клиент не управляет деньгами и сроками."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import Plan
from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus


class FakeYooKassa:
    """Узкая заглушка границы провайдера: проверяем HTTP-контракт, не transport."""

    def __init__(self) -> None:
        self.calls = 0

    async def create_payment(
        self,
        *,
        idempotence_key: str,
        amount_rub: Decimal,
        return_url: str,
        description: str,
        save_payment_method: bool,
    ) -> YooKassaPayment:
        self.calls += 1
        return YooKassaPayment(
            id=f"payment-{idempotence_key}",
            status=YooKassaPaymentStatus.pending,
            amount_rub=amount_rub,
            currency="RUB",
            confirmation_url=f"https://yookassa.test/{idempotence_key}",
        )

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_yookassa(monkeypatch: pytest.MonkeyPatch) -> FakeYooKassa:
    from repibot_api import subscription_view

    fake = FakeYooKassa()
    monkeypatch.setattr(subscription_view, "create_yookassa_client", lambda: fake, raising=False)
    return fake


def _payload(
    plan_id: int,
    *,
    purpose: str = "purchase",
    key: str = "7ba4f38a-7778-4a53-a8c5-d0fdd9d2f794",
) -> dict[str, object]:
    return {
        "plan_id": plan_id,
        "purpose": purpose,
        "provider": "yookassa",
        "idempotency_key": key,
        "save_payment_method": True,
    }


async def test_create_manual_yookassa_order_returns_confirm_url(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Without server-side snapshotting, a client price field could buy a cheaper plan."""
    response = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["confirmation_url"].startswith("https://yookassa.test/")
    assert body["status"] == "pending"
    assert body["price_rub"] == "299.00"
    assert body["amount_due_rub"] == "299.00"
    assert body["duration_days"] == 30
    assert datetime.fromisoformat(body["expires_at"]).tzinfo is not None
    assert set(body) == {
        "id",
        "purpose",
        "plan_id",
        "plan_code",
        "plan_name",
        "duration_days",
        "price_rub",
        "price_stars",
        "gross_rub",
        "discount_rub",
        "amount_due_rub",
        "status",
        "expires_at",
        "confirmation_url",
    }


async def test_orders_require_authentication(api_client: AsyncClient, month_plan: int) -> None:
    """Removing current_context must not expose a payment-start endpoint."""
    response = await api_client.post("/api/me/orders", json=_payload(month_plan))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_unconfigured_yookassa_is_a_stable_provider_error(
    api_client: AsyncClient, user_headers: dict[str, str], month_plan: int
) -> None:
    """A missing provider configuration must not leak as an internal error."""
    response = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"


@pytest.mark.parametrize(
    ("field", "value"), [("is_active", False), ("is_visible", False), ("is_trial", True)]
)
async def test_create_order_rejects_unavailable_plan(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
    engine: AsyncEngine,
    field: str,
    value: bool,
) -> None:
    """Changing an active, visible paid plan into an unavailable one must block checkout."""
    async with create_session_factory(engine)() as session:
        await session.execute(update(Plan).where(Plan.id == month_plan).values({field: value}))
        await session.commit()

    response = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "plan_inactive"
    assert fake_yookassa.calls == 0


async def test_gift_order_without_promo_is_rejected(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Dropping the gift/promo rule must never accidentally sell an untracked gift."""
    response = await api_client.post(
        "/api/me/orders", json=_payload(month_plan, purpose="gift"), headers=user_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "promo_unavailable"
    assert fake_yookassa.calls == 0


async def test_same_client_key_returns_same_order(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Removing idempotency would create two payable orders for one click retry."""
    first = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )
    second = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["confirmation_url"] == first.json()["confirmation_url"]
    assert fake_yookassa.calls == 1


async def test_order_creation_is_limited_by_user_and_ip(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Removing either rate-limit key lets a signed-in script create unlimited payments."""
    for index in range(5):
        response = await api_client.post(
            "/api/me/orders",
            json=_payload(month_plan, key=f"7ba4f38a-7778-4a53-a8c5-d0fdd9d2f{index:03d}"),
            headers={**user_headers, "X-Forwarded-For": "203.0.113.5"},
        )
        assert response.status_code == 201

    blocked = await api_client.post(
        "/api/me/orders",
        json=_payload(month_plan, key="7ba4f38a-7778-4a53-a8c5-d0fdd9d2f999"),
        headers={**user_headers, "X-Forwarded-For": "203.0.113.5"},
    )

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in blocked.headers


async def test_list_and_get_orders_are_scoped_to_current_user(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """A missing user predicate would expose another person's checkout history."""
    created = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )
    order_id = created.json()["id"]

    listed = await api_client.get("/api/me/orders", headers=user_headers)
    fetched = await api_client.get(f"/api/me/orders/{order_id}", headers=user_headers)

    assert listed.status_code == 200
    assert [order["id"] for order in listed.json()] == [order_id]
    assert fetched.status_code == 200
    assert fetched.json()["id"] == order_id
