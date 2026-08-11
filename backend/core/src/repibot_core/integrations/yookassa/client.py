"""Минимальный асинхронный транспорт к YooKassa API."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx

from repibot_core.integrations.yookassa.types import (
    YooKassaBindingStatus,
    YooKassaCardBinding,
    YooKassaPayment,
    YooKassaPaymentStatus,
)
from repibot_core.settings import get_settings


class YooKassaError(Exception):
    """YooKassa не приняла запрос или вернула неполный платёж."""


# httpx по умолчанию ждёт пять секунд на всё, включая чтение ответа. Для
# провайдера денег этого мало: обрыв на создании платежа оставляет платёж с
# неизвестной судьбой, который приходится доискивать сверкой. Соединение при
# этом должно устанавливаться быстро — на этом шаге ждать нечего.
TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)

# Повторяется только неудавшееся подключение: запрос при этом ещё не ушёл, и
# задвоить списание такой повтор не может. Повторять сам ответ нельзя даже с
# ключом идемпотентности — решение о повторе принимает вызывающий код.
CONNECT_RETRIES = 2


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
            timeout=TIMEOUT,
            transport=transport or httpx.AsyncHTTPTransport(retries=CONNECT_RETRIES),
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

    async def create_card_binding(
        self, *, idempotence_key: str, return_url: str
    ) -> YooKassaCardBinding:
        """Просит проверить и запомнить карту, не списывая денег.

        Это отдельный ресурс провайдера: у привязки нет ни суммы, ни заказа,
        поэтому платёжный путь она не переиспользует.
        """
        response = await self._http.post(
            "/payment_methods",
            headers={"Idempotence-Key": idempotence_key},
            json={
                "type": "bank_card",
                "confirmation": {"type": "redirect", "return_url": return_url},
            },
        )
        response.raise_for_status()
        return self._parse_binding(response.json())

    async def get_card_binding(self, binding_id: str) -> YooKassaCardBinding:
        response = await self._http.get(f"/payment_methods/{binding_id}")
        response.raise_for_status()
        return self._parse_binding(response.json())

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
        method = payment_method if isinstance(payment_method, dict) else {}
        return YooKassaPayment(
            id=payment_id,
            status=status,
            amount_rub=amount_rub,
            currency=currency,
            confirmation_url=confirmation_url,
            payment_method_id=(str(method["id"]) if method.get("id") is not None else None),
            # Только точное True: провайдер присылает payment_method и у
            # платежей без сохранения, и принять его за привязанную карту
            # значит однажды попытаться списать с несохранённой.
            payment_method_saved=method.get("saved") is True,
            payment_method_title=(
                str(method["title"]) if method.get("title") is not None else None
            ),
        )

    @staticmethod
    def _parse_binding(payload: object) -> YooKassaCardBinding:
        if not isinstance(payload, dict):
            raise YooKassaError("YooKassa вернула не объект привязки")
        confirmation = payload.get("confirmation")
        try:
            binding_id = str(payload["id"])
            status = YooKassaBindingStatus(str(payload["status"]))
        except (KeyError, ValueError) as error:
            raise YooKassaError("YooKassa вернула неполную привязку") from error
        return YooKassaCardBinding(
            id=binding_id,
            status=status,
            saved=payload.get("saved") is True,
            title=(str(payload["title"]) if payload.get("title") is not None else None),
            confirmation_url=(
                str(confirmation["confirmation_url"])
                if isinstance(confirmation, dict)
                and confirmation.get("confirmation_url") is not None
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
