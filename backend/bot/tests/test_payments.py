"""Telegram Stars are confirmed in the bot, never in the Mini App."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.util import find_spec
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.storage.memory import MemoryStorage

from repibot_bot.main import build_dispatcher
from repibot_core.db.models import User

PAYMENTS_MODULE_EXISTS = find_spec("repibot_bot.handlers.payments") is not None


@dataclass
class FakePayments:
    approved: int | None
    finalized: list[int] = field(default_factory=list)

    async def authorize_stars_attempt(
        self, *, invoice_payload: str, user_id: int, total_amount: int
    ) -> int | None:
        self.seen = (invoice_payload, user_id, total_amount)
        return self.approved

    async def confirm_stars_success(
        self, *, invoice_payload: str, user_id: int, total_amount: int
    ) -> int | None:
        self.seen = (invoice_payload, user_id, total_amount)
        return self.approved

    async def finalize_success(self, attempt_id: int) -> None:
        self.finalized.append(attempt_id)


def _owner() -> User:
    return User(id=7, telegram_id=700_001, referral_code="STARS001", language="ru")


async def test_successful_stars_payment_finalizes_the_attempt() -> None:
    if not PAYMENTS_MODULE_EXISTS:
        return
    from repibot_bot.handlers.payments import handle_successful_payment

    payment_service = FakePayments(approved=91)
    message = MagicMock()
    message.successful_payment.invoice_payload = "opaque-attempt"
    message.successful_payment.total_amount = 199

    await handle_successful_payment(message, user=_owner(), payment_service=payment_service)

    assert payment_service.seen == ("opaque-attempt", 7, 199)
    assert payment_service.finalized == [91]


async def test_pre_checkout_rejects_expired_or_inactive_attempt() -> None:
    if not PAYMENTS_MODULE_EXISTS:
        return
    from repibot_bot.handlers.payments import handle_pre_checkout

    payment_service = FakePayments(approved=None)
    query = MagicMock()
    query.invoice_payload = "expired-attempt"
    query.total_amount = 199
    query.answer = AsyncMock()

    await handle_pre_checkout(query, user=_owner(), payment_service=payment_service)

    query.answer.assert_awaited_once_with(ok=False, error_message="Счёт больше не активен")


async def test_pre_checkout_rejects_wrong_stars_amount() -> None:
    if not PAYMENTS_MODULE_EXISTS:
        return
    from repibot_bot.handlers.payments import handle_pre_checkout

    payment_service = FakePayments(approved=None)
    query = MagicMock()
    query.invoice_payload = "opaque-attempt"
    query.total_amount = 198
    query.answer = AsyncMock()

    await handle_pre_checkout(query, user=_owner(), payment_service=payment_service)

    query.answer.assert_awaited_once_with(ok=False, error_message="Счёт больше не активен")


async def test_duplicate_or_foreign_successful_payment_is_not_finalized() -> None:
    if not PAYMENTS_MODULE_EXISTS:
        return
    from repibot_bot.handlers.payments import handle_successful_payment

    payment_service = FakePayments(approved=None)
    message = MagicMock()
    message.successful_payment.invoice_payload = "opaque-attempt"
    message.successful_payment.total_amount = 199
    stranger = User(id=8, telegram_id=800_001, referral_code="STARS002", language="ru")

    await handle_successful_payment(message, user=stranger, payment_service=payment_service)
    await handle_successful_payment(message, user=stranger, payment_service=payment_service)

    assert payment_service.finalized == []


def test_dispatcher_registers_payment_router() -> None:
    assert PAYMENTS_MODULE_EXISTS
    dispatcher = build_dispatcher(MemoryStorage())

    assert any(router.name == "payments" for router in dispatcher.sub_routers)
