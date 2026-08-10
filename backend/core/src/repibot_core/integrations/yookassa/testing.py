"""Детерминированная заглушка YooKassa для проверок границы провайдера."""

from __future__ import annotations

from decimal import Decimal

import httpx

from repibot_core.integrations.yookassa.types import (
    YooKassaBindingStatus,
    YooKassaCardBinding,
    YooKassaPayment,
    YooKassaPaymentStatus,
)


class FakeYooKassa:
    def __init__(self) -> None:
        self._payments: dict[str, YooKassaPayment] = {}
        self._bindings: dict[str, YooKassaCardBinding] = {}

    def set_payment(self, payment_id: str, *, status: str, amount: str, currency: str) -> None:
        self._payments[payment_id] = YooKassaPayment(
            id=payment_id,
            status=YooKassaPaymentStatus(status),
            amount_rub=Decimal(amount),
            currency=currency,
            confirmation_url=f"https://yookassa.test/{payment_id}",
        )

    def set_binding(self, binding_id: str, *, status: str, saved: bool) -> None:
        self._bindings[binding_id] = YooKassaCardBinding(
            id=binding_id,
            status=YooKassaBindingStatus(status),
            saved=saved,
            title="Bank card *4444" if saved else None,
            confirmation_url=f"https://yookassa.test/bindings/{binding_id}",
        )

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        payment = self._payments.get(payment_id)
        if payment is None:
            # Привязка живёт в другом ресурсе провайдера, и её идентификатор в
            # платежах отсутствует. Настоящая YooKassa отвечает на такой запрос
            # 404, и код приёма обязан переживать именно это, а не KeyError.
            raise self._not_found(f"/payments/{payment_id}")
        return payment

    async def get_card_binding(self, binding_id: str) -> YooKassaCardBinding:
        binding = self._bindings.get(binding_id)
        if binding is None:
            raise self._not_found(f"/payment_methods/{binding_id}")
        return binding

    async def aclose(self) -> None:
        return None

    @staticmethod
    def _not_found(path: str) -> httpx.HTTPStatusError:
        request = httpx.Request("GET", f"https://yookassa.test{path}")
        response = httpx.Response(404, request=request, json={"description": "not found"})
        return httpx.HTTPStatusError("not found", request=request, response=response)
