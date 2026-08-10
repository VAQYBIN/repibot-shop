"""Транспорт YooKassa отправляет провайдеру неизменяемый снимок заказа."""

from __future__ import annotations

import json
from decimal import Decimal

import httpx

from repibot_core.integrations.yookassa.client import YooKassaClient
from repibot_core.integrations.yookassa.types import (
    YooKassaBindingStatus,
    YooKassaPayment,
    YooKassaPaymentStatus,
)
from repibot_core.services.payments import PaymentService


async def test_create_payment_uses_basic_auth_idempotence_key_and_snapped_amount() -> None:
    """Другой ключ или сумма во float списали бы дважды или не столько."""
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
    """Данные webhook не превращают непроверенный платёж в успешный."""

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
    """Ложный флаг переопределил бы поведение YooKassa для будущего продления."""
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

    body = seen["body"]
    assert isinstance(body, dict)
    assert "save_payment_method" not in body


async def test_mismatched_provider_response_id_is_rejected_before_database_access() -> None:
    """Поиск по подменённому id из ответа изменил бы чужую попытку."""

    class FailingSession:
        def begin(self) -> object:
            raise AssertionError("database must not be touched")

    class MismatchedProvider:
        async def get_payment(self, payment_id: str) -> YooKassaPayment:
            assert payment_id == "requested-payment"
            return YooKassaPayment(
                id="substituted-payment",
                status=YooKassaPaymentStatus.succeeded,
                amount_rub=Decimal("254.15"),
                currency="RUB",
                confirmation_url=None,
            )

    result = await PaymentService(FailingSession()).verify_yookassa_callback(  # type: ignore[arg-type]
        "requested-payment", MismatchedProvider()
    )

    assert result is None


def _client(handle: object) -> YooKassaClient:
    return YooKassaClient(
        shop_id="shop-id",
        secret_key="secret-key",
        base_url="https://yookassa.test/v3",
        transport=httpx.MockTransport(handle),  # type: ignore[arg-type]
    )


async def test_saved_card_is_read_from_the_provider_response() -> None:
    """Наш запрос не доказывает привязку: галочку ставит плательщик на форме."""

    async def handle(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "id": "payment-3",
                "status": "succeeded",
                "amount": {"value": "299.00", "currency": "RUB"},
                "payment_method": {
                    "type": "bank_card",
                    "id": "method-1",
                    "saved": True,
                    "title": "Bank card *4444",
                },
            },
        )

    client = _client(handle)
    try:
        payment = await client.get_payment("payment-3")
    finally:
        await client.aclose()

    assert payment.payment_method_saved is True
    assert payment.payment_method_title == "Bank card *4444"
    assert payment.payment_method_id == "method-1"


async def test_unsaved_method_is_not_mistaken_for_a_stored_card() -> None:
    """YooKassa присылает payment_method.id и когда карту не сохраняли."""

    async def handle(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "id": "payment-4",
                "status": "succeeded",
                "amount": {"value": "299.00", "currency": "RUB"},
                "payment_method": {"type": "bank_card", "id": "method-2"},
            },
        )

    client = _client(handle)
    try:
        payment = await client.get_payment("payment-4")
    finally:
        await client.aclose()

    assert payment.payment_method_id == "method-2"
    assert payment.payment_method_saved is False
    assert payment.payment_method_title is None


async def test_card_binding_is_created_as_a_separate_provider_resource() -> None:
    """Привязка без списания живёт в /payment_methods, а не в платежах."""
    seen: dict[str, object] = {}

    async def handle(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["idempotence_key"] = request.headers["idempotence-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "binding-1",
                "type": "bank_card",
                "status": "pending",
                "saved": False,
                "confirmation": {"type": "redirect", "confirmation_url": "https://pay.test/bind"},
            },
        )

    client = _client(handle)
    try:
        binding = await client.create_card_binding(
            idempotence_key="binding-key", return_url="https://app.test/account/payments"
        )
    finally:
        await client.aclose()

    assert seen["path"] == "/v3/payment_methods"
    assert seen["idempotence_key"] == "binding-key"
    assert seen["body"] == {
        "type": "bank_card",
        "confirmation": {"type": "redirect", "return_url": "https://app.test/account/payments"},
    }
    assert binding.id == "binding-1"
    assert binding.status is YooKassaBindingStatus.pending
    assert binding.saved is False
    assert binding.confirmation_url == "https://pay.test/bind"


async def test_card_binding_state_is_read_back_from_the_provider() -> None:
    """Возврат пользователя по redirect ничего не подтверждает."""

    async def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/payment_methods/binding-1"
        return httpx.Response(
            200,
            json={
                "id": "binding-1",
                "type": "bank_card",
                "status": "active",
                "saved": True,
                "title": "Bank card *4444",
            },
        )

    client = _client(handle)
    try:
        binding = await client.get_card_binding("binding-1")
    finally:
        await client.aclose()

    assert binding.status is YooKassaBindingStatus.active
    assert binding.saved is True
    assert binding.title == "Bank card *4444"
