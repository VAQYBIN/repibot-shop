"""Минимальный асинхронный транспорт к YooKassa API."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx

from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus
from repibot_core.settings import get_settings


class YooKassaError(Exception):
    """YooKassa не приняла запрос или вернула неполный платёж."""


class YooKassaClient:
    def __init__(
        self,
        *,
        shop_id: str,
        secret_key: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            auth=(shop_id, secret_key),
            headers={"Content-Type": "application/json"},
            transport=transport,
        )

    async def create_payment(
        self,
        *,
        idempotence_key: str,
        amount_rub: Decimal,
        return_url: str,
        description: str,
        save_payment_method: bool,
        payment_method_id: str | None = None,
    ) -> YooKassaPayment:
        amount = amount_rub.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        payload: dict[str, object] = {
            "amount": {"value": format(amount, ".2f"), "currency": "RUB"},
            "capture": True,
            "description": description,
        }
        if payment_method_id is None:
            payload["confirmation"] = {"type": "redirect", "return_url": return_url}
        else:
            payload["payment_method_id"] = payment_method_id
        if save_payment_method:
            payload["save_payment_method"] = True
        response = await self._http.post(
            "/payments",
            headers={"Idempotence-Key": idempotence_key},
            json=payload,
        )
        response.raise_for_status()
        return self._parse_payment(response.json())

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        response = await self._http.get(f"/payments/{payment_id}")
        response.raise_for_status()
        return self._parse_payment(response.json())

    async def aclose(self) -> None:
        await self._http.aclose()

    @staticmethod
    def _parse_payment(payload: object) -> YooKassaPayment:
        if not isinstance(payload, dict):
            raise YooKassaError("YooKassa вернула не объект платежа")
        amount = payload.get("amount")
        confirmation = payload.get("confirmation")
        payment_method = payload.get("payment_method")
        try:
            payment_id = str(payload["id"])
            status = YooKassaPaymentStatus(str(payload["status"]))
            if not isinstance(amount, dict):
                raise ValueError
            amount_rub = Decimal(str(amount["value"]))
            currency = str(amount["currency"])
        except (KeyError, InvalidOperation, ValueError) as error:
            raise YooKassaError("YooKassa вернула неполный платёж") from error
        confirmation_url = (
            str(confirmation["confirmation_url"])
            if isinstance(confirmation, dict) and confirmation.get("confirmation_url") is not None
            else None
        )
        return YooKassaPayment(
            id=payment_id,
            status=status,
            amount_rub=amount_rub,
            currency=currency,
            confirmation_url=confirmation_url,
            payment_method_id=(
                str(payment_method["id"])
                if isinstance(payment_method, dict) and payment_method.get("id") is not None
                else None
            ),
        )


def create_yookassa_client() -> YooKassaClient:
    settings = get_settings()
    shop_id = settings.yookassa_shop_id
    secret_key = settings.yookassa_secret_key.get_secret_value()
    if not shop_id or not secret_key:
        raise YooKassaError("YooKassa не настроена")
    return YooKassaClient(
        shop_id=shop_id,
        secret_key=secret_key,
        base_url=settings.yookassa_api_base_url,
    )
