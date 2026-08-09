"""Детерминированная заглушка YooKassa для проверок границы провайдера."""

from __future__ import annotations

from decimal import Decimal

from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus


class FakeYooKassa:
    def __init__(self) -> None:
        self._payments: dict[str, YooKassaPayment] = {}

    def set_payment(
        self, payment_id: str, *, status: str, amount: str, currency: str
    ) -> None:
        self._payments[payment_id] = YooKassaPayment(
            id=payment_id,
            status=YooKassaPaymentStatus(status),
            amount_rub=Decimal(amount),
            currency=currency,
            confirmation_url=f"https://yookassa.test/{payment_id}",
        )

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        return self._payments[payment_id]

    async def aclose(self) -> None:
        return None
