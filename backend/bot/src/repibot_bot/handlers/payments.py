"""Telegram Stars boundary: Telegram proves payment, core grants the entitlement."""

from __future__ import annotations

from typing import Protocol

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery

from repibot_core.db.models import User

_INACTIVE_INVOICE = "Счёт больше не активен"


class StarsInvoiceView(Protocol):
    title: str
    description: str
    invoice_payload: str
    price_stars: int


class StarsPaymentService(Protocol):
    async def next_stars_invoice(
        self, user_id: int, handoff_reference: str
    ) -> StarsInvoiceView | None: ...

    async def authorize_stars_attempt(
        self,
        *,
        invoice_payload: str,
        user_id: int,
        total_amount: int,
        currency: str,
        pre_checkout_id: str,
    ) -> int | None: ...

    async def confirm_stars_success(
        self,
        *,
        invoice_payload: str,
        user_id: int,
        total_amount: int,
        currency: str,
        telegram_payment_charge_id: str,
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
        currency=query.currency,
        pre_checkout_id=query.id,
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
        currency=payment.currency,
        telegram_payment_charge_id=payment.telegram_payment_charge_id,
    )
    if attempt_id is not None:
        await payment_service.finalize_success(attempt_id)


async def handle_stars_handoff(
    message: Message,
    command: CommandObject,
    user: User,
    payment_service: StarsPaymentService,
) -> None:
    """Issues the invoice only in the authenticated Telegram chat of its owner."""
    if (
        message.chat.type != "private"
        or user.telegram_id is None
        or message.chat.id != user.telegram_id
    ):
        return
    handoff_reference = (command.args or "").removeprefix("pay_")
    if not handoff_reference:
        return
    invoice = await payment_service.next_stars_invoice(user.id, handoff_reference)
    if invoice is None:
        return
    await message.answer_invoice(
        title=invoice.title,
        description=invoice.description,
        payload=invoice.invoice_payload,
        currency="XTR",
        prices=[LabeledPrice(label=invoice.title, amount=invoice.price_stars)],
    )


def build_payment_router() -> Router:
    router = Router(name="payments")
    router.message.register(
        handle_stars_handoff, CommandStart(deep_link=True, magic=F.args.startswith("pay_"))
    )
    router.pre_checkout_query.register(handle_pre_checkout)
    router.message.register(handle_successful_payment, F.successful_payment)
    return router
