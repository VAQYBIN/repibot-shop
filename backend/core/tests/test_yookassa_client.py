"""YooKassa transport sends an immutable commercial snapshot to the provider."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx

from repibot_core.integrations.yookassa.client import YooKassaClient
from repibot_core.integrations.yookassa.types import YooKassaPaymentStatus


async def test_create_payment_uses_basic_auth_idempotence_key_and_snapped_amount() -> None:
    """A changed key or a float amount could charge twice or for a different sum."""
    seen: dict[str, object] = {}

    async def handle(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        seen["idempotence_key"] = request.headers["idempotence-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "payment-1",
                "status": "pending",
                "amount": {"value": "254.15", "currency": "RUB"},
                "confirmation": {"type": "redirect", "confirmation_url": "https://pay.test/1"},
            },
        )

    client = YooKassaClient(
        shop_id="shop-id",
        secret_key="secret-key",
        base_url="https://yookassa.test/v3",
        transport=httpx.MockTransport(handle),
    )
    try:
        payment = await client.create_payment(
            idempotence_key="stable-attempt-key",
            amount_rub=Decimal("254.15"),
            return_url="https://app.test/payments/return",
            description="Заказ #12",
            save_payment_method=True,
        )
    finally:
        await client.aclose()

    assert seen["authorization"] == "Basic c2hvcC1pZDpzZWNyZXQta2V5"
    assert seen["idempotence_key"] == "stable-attempt-key"
    assert seen["body"] == {
        "amount": {"value": "254.15", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": "https://app.test/payments/return"},
        "description": "Заказ #12",
        "save_payment_method": True,
    }
    assert payment.id == "payment-1"
    assert payment.confirmation_url == "https://pay.test/1"


async def test_get_payment_parses_provider_truth_without_webhook_fields() -> None:
    """Webhook data must never be able to turn an unverified payment into success."""
    async def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/payments/payment-1"
        return httpx.Response(
            200,
            json={
                "id": "payment-1",
                "status": "succeeded",
                "amount": {"value": "254.15", "currency": "RUB"},
                "confirmation": {"type": "redirect", "confirmation_url": "https://pay.test/1"},
            },
        )

    client = YooKassaClient(
        shop_id="shop-id",
        secret_key="secret-key",
        base_url="https://yookassa.test/v3",
        transport=httpx.MockTransport(handle),
    )
    try:
        payment = await client.get_payment("payment-1")
    finally:
        await client.aclose()

    assert payment.status is YooKassaPaymentStatus.succeeded
    assert payment.amount_rub == Decimal("254.15")
    assert payment.currency == "RUB"


async def test_create_payment_omits_method_saving_when_not_requested() -> None:
    """Sending a false flag can override YooKassa defaults for a later renewal flow."""
    seen: dict[str, object] = {}

    async def handle(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "payment-2",
                "status": "pending",
                "amount": {"value": "254.15", "currency": "RUB"},
            },
        )

    client = YooKassaClient(
        shop_id="shop-id",
        secret_key="secret-key",
        base_url="https://yookassa.test/v3",
        transport=httpx.MockTransport(handle),
    )
    try:
        await client.create_payment(
            idempotence_key="stable-attempt-key",
            amount_rub=Decimal("254.15"),
            return_url="https://app.test/payments/return",
            description="Заказ #12",
            save_payment_method=False,
        )
    finally:
        await client.aclose()

    assert "save_payment_method" not in seen["body"]
