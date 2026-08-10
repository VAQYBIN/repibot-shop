"""The E2E payment provider must preserve the commercial provider boundary."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx

from repibot_core.integrations.yookassa.types import YooKassaPaymentStatus
from repibot_core.testing.yookassa import FakeYooKassa, create_yookassa_app


async def test_fake_yookassa_creates_idempotently_and_exposes_provider_truth() -> None:
    """A fake that changes the payment snapshot would hide amount/currency regressions."""
    fake = FakeYooKassa()

    first = await fake.create_payment(
        idempotence_key="commercial-key-41",
        amount_rub=Decimal("254.15"),
        return_url="http://localhost:8081/account/payments",
        description="Заказ #41",
        save_payment_method=True,
    )
    replay = await fake.create_payment(
        idempotence_key="commercial-key-41",
        amount_rub=Decimal("254.15"),
        return_url="http://localhost:8081/account/payments",
        description="Заказ #41",
        save_payment_method=True,
    )

    assert replay == first
    assert first.status is YooKassaPaymentStatus.pending
    assert first.amount_rub == Decimal("254.15")
    assert first.currency == "RUB"
    assert first.confirmation_url is not None

    await fake.set_status(first.id, YooKassaPaymentStatus.succeeded)
    stored = await fake.get_payment(first.id)
    assert stored.status is YooKassaPaymentStatus.succeeded
    assert stored.amount_rub == Decimal("254.15")
    assert stored.currency == "RUB"


async def test_fake_yookassa_can_hold_a_poll_while_a_webhook_changes_status() -> None:
    """Without this interleaving, callback-versus-poll races never reach E2E."""
    fake = FakeYooKassa()
    payment = await fake.create_payment(
        idempotence_key="race-key-9",
        amount_rub=Decimal("299.00"),
        return_url="http://localhost:8081/account/payments",
        description="Заказ #9",
        save_payment_method=False,
    )

    fake.pause_gets()
    poll = asyncio.create_task(fake.get_payment(payment.id))
    await fake.wait_for_get()
    await fake.set_status(payment.id, YooKassaPaymentStatus.succeeded)
    fake.release_gets()

    assert (await poll).status is YooKassaPaymentStatus.succeeded


async def test_fake_yookassa_keeps_recurring_payment_ids_distinct_for_one_method() -> None:
    """A saved payment method identifies the instrument, never the provider payment."""
    fake = FakeYooKassa()
    first = await fake.create_payment(
        idempotence_key="renewal-24h",
        amount_rub=Decimal("299.00"),
        return_url="http://localhost/renewal",
        description="renewal one",
        save_payment_method=False,
        payment_method_id="saved-method-1",
    )
    second = await fake.create_payment(
        idempotence_key="renewal-plus-6h",
        amount_rub=Decimal("299.00"),
        return_url="http://localhost/renewal",
        description="renewal two",
        save_payment_method=False,
        payment_method_id="saved-method-1",
    )

    assert first.id != second.id
    assert first.payment_method_id == second.payment_method_id == "saved-method-1"
    assert await fake.get_payment(first.id) == first
    assert await fake.get_payment(second.id) == second


async def test_fake_yookassa_http_replay_keeps_the_original_commercial_snapshot() -> None:
    """A changed-currency replay must not rewrite the payment the key already owns."""
    app = create_yookassa_app()
    transport = httpx.ASGITransport(app=app)
    headers = {"Idempotence-Key": "immutable-replay-key"}
    first_payload = {
        "amount": {"value": "254.15", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "http://return.test/payments"},
    }
    malicious_replay = {
        "amount": {"value": "999.99", "currency": "USD"},
        "confirmation": {"type": "redirect", "return_url": "http://return.test/payments"},
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://yookassa.test") as client:
        first = await client.post("/v3/payments", headers=headers, json=first_payload)
        payment_id = first.json()["id"]
        status = await client.post(
            f"/__e2e/payments/{payment_id}/status", json={"status": "succeeded"}
        )
        replay = await client.post("/v3/payments", headers=headers, json=malicious_replay)
        stored = await client.get(f"/v3/payments/{payment_id}")

    assert first.status_code == 200
    assert status.status_code == 204
    assert replay.status_code == 200
    assert replay.json()["id"] == payment_id
    assert replay.json()["status"] == "succeeded"
    assert replay.json()["amount"] == {"value": "254.15", "currency": "RUB"}
    assert stored.json()["id"] == payment_id
    assert stored.json()["status"] == "succeeded"
    assert stored.json()["amount"] == {"value": "254.15", "currency": "RUB"}
