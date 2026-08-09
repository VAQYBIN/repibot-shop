"""The E2E payment provider must preserve the commercial provider boundary."""

from __future__ import annotations

import asyncio
from decimal import Decimal

from repibot_core.integrations.yookassa.types import YooKassaPaymentStatus
from repibot_core.testing.yookassa import FakeYooKassa


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
