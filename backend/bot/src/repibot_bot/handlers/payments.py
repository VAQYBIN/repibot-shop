"""Telegram Stars boundary: Telegram proves payment, core grants the entitlement."""

from __future__ import annotations

from typing import Protocol

from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from repibot_core.db.models import User

_INACTIVE_INVOICE = "Счёт больше не активен"


class StarsPaymentService(Protocol):
    async def authorize_stars_attempt(
        self, *, invoice_payload: str, user_id: int, total_amount: int
    ) -> int | None: ...

    async def confirm_stars_success(
        self, *, invoice_payload: str, user_id: int, total_amount: int
    ) -> int | None: ...

    async def finalize_success(self, attempt_id: int) -> object: ...


async def handle_pre_checkout(
    query: PreCheckoutQuery, user: User, payment_service: StarsPaymentService
) -> None:
    """Lets Telegram charge only the exact pending Stars attempt of its owner."""
    attempt_id = await payment_service.authorize_stars_attempt(
        invoice_payload=query.invoice_payload,
        user_id=user.id,
        total_amount=query.total_amount,
    )
    if attempt_id is None:
        await query.answer(ok=False, error_message=_INACTIVE_INVOICE)
        return
    await query.answer(ok=True)


async def handle_successful_payment(
    message: Message, user: User, payment_service: StarsPaymentService
) -> None:
    """Records the signed Telegram update then reuses the provider-neutral finalizer."""
    payment = message.successful_payment
    if payment is None:
        return
    attempt_id = await payment_service.confirm_stars_success(
        invoice_payload=payment.invoice_payload,
        user_id=user.id,
        total_amount=payment.total_amount,
    )
    if attempt_id is not None:
        await payment_service.finalize_success(attempt_id)


def build_payment_router() -> Router:
    router = Router(name="payments")
    router.pre_checkout_query.register(handle_pre_checkout)
    router.message.register(handle_successful_payment, F.successful_payment)
    return router
