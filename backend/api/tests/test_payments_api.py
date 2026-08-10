"""Публичный контракт ручных заказов: клиент не управляет деньгами и сроками."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import Order, OrderStatus, PaymentAttempt, PaymentStatus, Plan
from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus


class FakeYooKassa:
    """Узкая заглушка границы провайдера: проверяем HTTP-контракт, не transport."""

    def __init__(self) -> None:
        self.calls = 0
        self.closed = 0
        self.return_urls: list[str] = []

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
        self.return_urls.append(return_url)
        return YooKassaPayment(
            id=f"payment-{idempotence_key}",
            status=YooKassaPaymentStatus.pending,
            amount_rub=amount_rub,
            currency="RUB",
            confirmation_url=f"https://yookassa.test/{idempotence_key}",
        )

    async def aclose(self) -> None:
        self.closed += 1


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


def _stars_payload(plan_id: int) -> dict[str, object]:
    return {
        "plan_id": plan_id,
        "purpose": "purchase",
        "provider": "stars",
        "idempotency_key": "stars-7ba4f38a-7778-4a53-a8c5-d0fdd9d2f794",
    }


async def test_create_stars_order_requires_telegram_invoice(
    api_client: AsyncClient,
    telegram_user_headers: dict[str, str],
    month_plan: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from repibot_api.routers import subscription as subscription_router

    async def handoff_url(*_args: object) -> str:
        return "https://t.me/repibot?start=pay_opaque-handoff-reference"

    monkeypatch.setattr(subscription_router, "stars_handoff_url", handoff_url)
    started = datetime.now(UTC)
    response = await api_client.post(
        "/api/me/orders", json=_stars_payload(month_plan), headers=telegram_user_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["telegram_invoice_required"] is True
    assert body["confirmation_url"] is None
    assert body["telegram_handoff_url"] == "https://t.me/repibot?start=pay_opaque-handoff-reference"
    assert body["price_stars"] == 199
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert expires_at.tzinfo is not None
    assert timedelta(minutes=14) < expires_at - started <= timedelta(minutes=15, seconds=1)


async def test_create_manual_yookassa_order_returns_confirm_url(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Без серверного снимка поле цены от клиента купило бы тариф дешевле."""
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
        "telegram_invoice_required",
        "telegram_handoff_url",
    }


async def test_provider_client_is_closed_before_the_response_is_returned(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Клиент провайдера закрывается на каждом заказе, а не когда придёт сборщик.

    Тест стережёт сам факт закрытия: без него брошенный httpx.AsyncClient — это
    сокеты, растущие с каждой покупкой.
    """
    response = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert response.status_code == 201
    assert fake_yookassa.closed == 1


async def test_orders_require_authentication(api_client: AsyncClient, month_plan: int) -> None:
    """Снятый current_context открыл бы вход в оплату кому угодно."""
    response = await api_client.post("/api/me/orders", json=_payload(month_plan))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_unconfigured_yookassa_is_a_stable_provider_error(
    api_client: AsyncClient, user_headers: dict[str, str], month_plan: int
) -> None:
    """Ненастроенный провайдер не должен выглядеть внутренней ошибкой."""
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
    """Ставший недоступным тариф закрывает оформление, а не продаётся дальше."""
    async with create_session_factory(engine)() as session:
        await session.execute(update(Plan).where(Plan.id == month_plan).values({field: value}))
        await session.commit()

    response = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "plan_inactive"
    assert fake_yookassa.calls == 0


async def test_gift_order_is_paid_without_a_promo(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Подарок — назначение оплаченного заказа, а не побочный эффект промокода."""
    response = await api_client.post(
        "/api/me/orders", json=_payload(month_plan, purpose="gift"), headers=user_headers
    )

    assert response.status_code == 201
    assert response.json()["purpose"] == "gift"
    assert fake_yookassa.calls == 1


async def test_same_client_key_returns_same_order(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Без идемпотентности повторный клик создал бы два оплачиваемых заказа."""
    first = await api_client.post("/api/me/orders", json=_payload(month_plan), headers=user_headers)
    second = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["confirmation_url"] == first.json()["confirmation_url"]
    assert fake_yookassa.calls == 1


async def test_maximum_length_client_key_is_safe_for_provider_idempotency(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Принятый ключ в 128 символов не должен переполнять provider_key."""
    response = await api_client.post(
        "/api/me/orders", json=_payload(month_plan, key="k" * 128), headers=user_headers
    )

    assert response.status_code == 201
    assert fake_yookassa.calls == 1


async def test_concurrent_first_retries_return_the_same_order(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Два одновременных чтения отсутствующего заказа не должны отдать 500."""
    requests = [
        api_client.post(
            "/api/me/orders",
            json=_payload(month_plan, key="concurrent-first-order"),
            headers=user_headers,
        )
        for _ in range(2)
    ]
    first, second = await asyncio.gather(*requests, return_exceptions=True)

    assert isinstance(first, Response)
    assert isinstance(second, Response)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert fake_yookassa.calls == 1


async def test_fulfilled_order_replay_never_reopens_provider_payment(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
    engine: AsyncEngine,
) -> None:
    """Повтор завершённого заказа не должен переписать данные проверки платежа."""
    created = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )
    order_id = created.json()["id"]
    async with create_session_factory(engine)() as session:
        await session.execute(
            update(Order).where(Order.id == order_id).values(status=OrderStatus.fulfilled)
        )
        await session.execute(
            update(PaymentAttempt)
            .where(PaymentAttempt.order_id == order_id)
            .values(
                status=PaymentStatus.succeeded,
                verified_payload={"amount": "299.00", "currency": "RUB", "status": "succeeded"},
            )
        )
        await session.commit()

    replay = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert replay.status_code == 201
    assert replay.json()["id"] == order_id
    assert replay.json()["confirmation_url"] is None
    assert fake_yookassa.calls == 1


async def test_same_key_replay_is_not_limited_after_unique_creates(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Ограничивать повторы значит отклонять безобидный сетевой ретрай."""
    first = await api_client.post("/api/me/orders", json=_payload(month_plan), headers=user_headers)
    for index in range(4):
        response = await api_client.post(
            "/api/me/orders",
            json=_payload(month_plan, key=f"other-create-{index}"),
            headers=user_headers,
        )
        assert response.status_code == 201

    replay = await api_client.post(
        "/api/me/orders", json=_payload(month_plan), headers=user_headers
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    assert fake_yookassa.calls == 5


async def test_order_creation_is_limited_by_user_and_ip(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
) -> None:
    """Без любого из двух ключей скрипт под входом наделает платежей без счёта."""
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
    """Забытый фильтр по пользователю показал бы чужую историю заказов."""
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


async def test_return_url_is_built_by_the_server_from_the_named_surface(
    api_client: AsyncClient,
    user_headers: dict[str, str],
    month_plan: int,
    fake_yookassa: FakeYooKassa,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Из Mini App возврат ведёт в Telegram, а не на страницу вне его.

    Клиент называет поверхность, а не адрес: принять URL из запроса значит
    согласиться увести плательщика с оплаты на чужой домен.
    """
    from repibot_api.routers import subscription as subscription_router
    from repibot_core.settings import get_settings

    monkeypatch.setattr(get_settings(), "public_web_url", "https://shop.test")

    async def bot_username(*_args: object) -> str:
        return "repibot"

    monkeypatch.setattr(subscription_router.BotApi, "username", bot_username, raising=False)

    from_web = await api_client.post(
        "/api/me/orders",
        json={**_payload(month_plan, key="surface-web"), "return_surface": "web"},
        headers=user_headers,
    )
    from_miniapp = await api_client.post(
        "/api/me/orders",
        json={**_payload(month_plan, key="surface-app"), "return_surface": "miniapp"},
        headers=user_headers,
    )

    assert (from_web.status_code, from_miniapp.status_code) == (201, 201)
    assert fake_yookassa.return_urls == [
        "https://shop.test/account/payments",
        "https://t.me/repibot",
    ]
