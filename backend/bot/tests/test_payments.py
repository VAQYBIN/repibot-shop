"""Telegram Stars are confirmed in the bot, never in the Mini App."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerPreCheckoutQuery, SendInvoice
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_bot.handlers.payments import build_payment_router
from repibot_bot.main import build_dispatcher
from repibot_core.db.models import Order, OrderStatus, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.services.payments import FinalizationResult, PaymentService

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

    async def next_stars_invoice(self, user_id: int) -> None:
        return None


@dataclass(frozen=True)
class FakeInvoice:
    title: str
    description: str
    invoice_payload: str
    price_stars: int


class FakeInvoicePayments:
    async def next_stars_invoice(self, user_id: int) -> FakeInvoice:
        assert user_id == 7
        return FakeInvoice(
            title="Month",
            description="VPN subscription",
            invoice_payload="stars.random-reference",
            price_stars=199,
        )


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.methods: list[object] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self, bot: Bot, method: Any, timeout: int | None = None  # noqa: ASYNC109
    ) -> Any:
        self.methods.append(method)
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,  # noqa: ASYNC109
        chunk_size: int = 65_536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes]:
        del url, headers, timeout, chunk_size, raise_for_status
        if False:
            yield b""


def _dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(build_payment_router())
    return dispatcher


def _start_pay_update(*, chat_type: str = "private") -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 0,
                "chat": {"id": 700_001, "type": chat_type},
                "from": {"id": 700_001, "is_bot": False, "first_name": "Test"},
                "text": "/start pay",
            },
        }
    )


def _successful_payment_update(payload: str, amount: int) -> Update:
    return Update.model_validate(
        {
            "update_id": 2,
            "message": {
                "message_id": 2,
                "date": 0,
                "chat": {"id": 700_001, "type": "private"},
                "from": {"id": 700_001, "is_bot": False, "first_name": "Test"},
                "successful_payment": {
                    "currency": "XTR",
                    "total_amount": amount,
                    "invoice_payload": payload,
                    "telegram_payment_charge_id": "tg-charge-1",
                    "provider_payment_charge_id": "",
                },
            },
        }
    )


def _pre_checkout_update(payload: str, amount: int) -> Update:
    return Update.model_validate(
        {
            "update_id": 3,
            "pre_checkout_query": {
                "id": "checkout-1",
                "from": {"id": 700_001, "is_bot": False, "first_name": "Test"},
                "currency": "XTR",
                "total_amount": amount,
                "invoice_payload": payload,
            },
        }
    )


async def _stars_order(session: AsyncSession) -> tuple[User, Order, str]:
    plan = await PlanRepository(session).create(
        code="stars-month",
        name={"ru": "Month", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=299,
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(telegram_id=700_001, referral_code="STARS001", language="ru")
    session.add(user)
    await session.commit()
    created = await PaymentService(session).create_stars_order(
        user_id=user.id,
        plan_id=plan.id,
        purpose="purchase",  # type: ignore[arg-type]
        client_key="stars-test-order",
        promo_code=None,
    )
    assert created.invoice_payload is not None
    return user, created.order, created.invoice_payload


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


async def test_pay_handoff_feed_update_sends_server_built_stars_invoice() -> None:
    session = RecordingSession()
    bot = Bot(token="123456:test-token", session=session)

    await _dispatcher().feed_update(
        bot, _start_pay_update(), user=_owner(), payment_service=FakeInvoicePayments()
    )

    sent = next(method for method in session.methods if isinstance(method, SendInvoice))
    assert sent.currency == "XTR"
    assert sent.provider_token is None
    assert sent.payload == "stars.random-reference"
    assert [price.amount for price in sent.prices] == [199]


async def test_pay_handoff_feed_update_sends_persisted_owner_invoice(
    db_session: AsyncSession,
) -> None:
    user, _order, payload = await _stars_order(db_session)
    session = RecordingSession()
    bot = Bot(token="123456:test-token", session=session)

    await _dispatcher().feed_update(
        bot,
        _start_pay_update(),
        user=user,
        payment_service=PaymentService(db_session),
    )

    sent = next(method for method in session.methods if isinstance(method, SendInvoice))
    assert sent.currency == "XTR"
    assert sent.payload == payload
    assert [price.amount for price in sent.prices] == [199]


async def test_pay_handoff_never_sends_an_owner_invoice_to_a_group() -> None:
    session = RecordingSession()
    bot = Bot(token="123456:test-token", session=session)

    await _dispatcher().feed_update(
        bot,
        _start_pay_update(chat_type="group"),
        user=_owner(),
        payment_service=FakeInvoicePayments(),
    )

    assert not any(isinstance(method, SendInvoice) for method in session.methods)


async def test_successful_payment_feed_update_finalizes_persisted_order_once(
    db_session: AsyncSession,
) -> None:
    user, order, payload = await _stars_order(db_session)
    bot = Bot(token="123456:test-token", session=RecordingSession())
    dispatcher = _dispatcher()

    class FailingFinalizer(PaymentService):
        async def finalize_success(
            self, *args: object, **kwargs: object
        ) -> FinalizationResult | None:
            raise RuntimeError(f"simulated finalizer crash for {args!r}/{kwargs!r}")

    with pytest.raises(RuntimeError, match="simulated finalizer crash"):
        await dispatcher.feed_update(
            bot,
            _successful_payment_update(payload, 199),
            user=user,
            payment_service=FailingFinalizer(db_session),
        )
    pending = await db_session.scalar(select(Order.status).where(Order.id == order.id))
    assert pending is OrderStatus.pending

    await dispatcher.feed_update(
        bot,
        _successful_payment_update(payload, 199),
        user=user,
        payment_service=PaymentService(db_session),
    )

    status = await db_session.scalar(select(Order.status).where(Order.id == order.id))
    assert status is OrderStatus.fulfilled


async def test_pre_checkout_feed_update_rejects_invalid_signature(
    db_session: AsyncSession,
) -> None:
    user, _order, _payload = await _stars_order(db_session)
    session = RecordingSession()
    bot = Bot(token="123456:test-token", session=session)

    await _dispatcher().feed_update(
        bot,
        _pre_checkout_update("stars.not-a-real-reference", 199),
        user=user,
        payment_service=PaymentService(db_session),
    )

    answer = next(
        method for method in session.methods if isinstance(method, AnswerPreCheckoutQuery)
    )
    assert answer.ok is False


@pytest.mark.parametrize("case", ["expired", "wrong_owner", "wrong_state", "wrong_amount"])
async def test_pre_checkout_feed_update_rejects_invalid_persisted_attempt(
    db_session: AsyncSession, case: str
) -> None:
    user, order, payload = await _stars_order(db_session)
    amount = 199
    owner = user
    if case == "expired":
        order.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db_session.commit()
    elif case == "wrong_owner":
        owner = User(id=user.id + 1, telegram_id=800_001, referral_code="STARS003", language="ru")
    elif case == "wrong_state":
        order.status = OrderStatus.canceled
        await db_session.commit()
    else:
        amount = 198

    session = RecordingSession()
    bot = Bot(token="123456:test-token", session=session)
    await _dispatcher().feed_update(
        bot,
        _pre_checkout_update(payload, amount),
        user=owner,
        payment_service=PaymentService(db_session),
    )

    answer = next(
        method for method in session.methods if isinstance(method, AnswerPreCheckoutQuery)
    )
    assert answer.ok is False
