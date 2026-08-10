"""Детерминированная замена YooKassa только для изолированного стенда E2E."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from itertools import count
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from repibot_core.integrations.yookassa.types import (
    YooKassaBindingStatus,
    YooKassaCardBinding,
    YooKassaPayment,
    YooKassaPaymentStatus,
)


class FakeYooKassa:
    """Состояние провайдера в памяти со швом для гонки webhook и опроса."""

    def __init__(self) -> None:
        self._payments: dict[str, YooKassaPayment] = {}
        self._keys: dict[str, str] = {}
        self._ids = count(1)
        self._latest_payment_id: str | None = None
        self._get_gate = asyncio.Event()
        self._get_gate.set()
        self._get_started = asyncio.Event()
        self._bindings: dict[str, YooKassaCardBinding] = {}
        self._binding_keys: dict[str, str] = {}
        # Плательщик решает на форме, запоминать ли карту. Сценарий стенда
        # выбирает это заранее, потому что настоящей формы в E2E нет.
        self.save_next_card = False

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
        """Повторяет идемпотентность YooKassa и отдаёт только разобранные поля."""
        del description, save_payment_method
        if idempotence_key in self._keys:
            return self._payments[self._keys[idempotence_key]]
        payment_id = f"fake-payment-{next(self._ids)}"
        payment = YooKassaPayment(
            id=payment_id,
            status=YooKassaPaymentStatus.pending,
            amount_rub=amount_rub,
            currency="RUB",
            confirmation_url=(
                None if payment_method_id is not None else f"{return_url}?payment={payment_id}"
            ),
            payment_method_id=("fake-method-1" if payment_method_id is None else payment_method_id),
            payment_method_saved=self.save_next_card and payment_method_id is None,
            payment_method_title=(
                "Bank card *4444" if self.save_next_card and payment_method_id is None else None
            ),
        )
        self._keys[idempotence_key] = payment_id
        self._payments[payment_id] = payment
        self._latest_payment_id = payment_id
        return payment

    async def create_card_binding(
        self, *, idempotence_key: str, return_url: str
    ) -> YooKassaCardBinding:
        if idempotence_key in self._binding_keys:
            return self._bindings[self._binding_keys[idempotence_key]]
        binding_id = f"fake-binding-{next(self._ids)}"
        binding = YooKassaCardBinding(
            id=binding_id,
            status=YooKassaBindingStatus.pending,
            saved=False,
            title=None,
            confirmation_url=f"{return_url}?binding={binding_id}",
        )
        self._binding_keys[idempotence_key] = binding_id
        self._bindings[binding_id] = binding
        return binding

    async def get_card_binding(self, binding_id: str) -> YooKassaCardBinding:
        return self._bindings[binding_id]

    async def set_binding(
        self, binding_id: str, *, status: YooKassaBindingStatus, saved: bool
    ) -> None:
        self._bindings[binding_id] = replace(
            self._bindings[binding_id],
            status=status,
            saved=saved,
            title="Bank card *4444" if saved else None,
        )

    async def get_payment(self, payment_id: str) -> YooKassaPayment:
        self._get_started.set()
        await self._get_gate.wait()
        return self._payments[payment_id]

    async def set_status(self, payment_id: str, status: YooKassaPaymentStatus) -> None:
        self._payments[payment_id] = replace(self._payments[payment_id], status=status)

    def pause_gets(self) -> None:
        self._get_started.clear()
        self._get_gate.clear()

    async def wait_for_get(self) -> None:
        await self._get_started.wait()

    def release_gets(self) -> None:
        self._get_gate.set()

    async def aclose(self) -> None:
        return None

    def latest_payment_id(self) -> str | None:
        return self._latest_payment_id


def _payment_json(payment: YooKassaPayment) -> dict[str, object]:
    body: dict[str, object] = {
        "id": payment.id,
        "status": payment.status.value,
        "amount": {"value": format(payment.amount_rub, ".2f"), "currency": payment.currency},
    }
    if payment.confirmation_url is not None:
        body["confirmation"] = {"type": "redirect", "confirmation_url": payment.confirmation_url}
    if payment.payment_method_id is not None:
        method: dict[str, object] = {"id": payment.payment_method_id, "type": "bank_card"}
        if payment.payment_method_saved:
            method["saved"] = True
            method["title"] = payment.payment_method_title
        body["payment_method"] = method
    return body


def _binding_json(binding: YooKassaCardBinding) -> dict[str, object]:
    body: dict[str, object] = {
        "id": binding.id,
        "type": "bank_card",
        "status": binding.status.value,
        "saved": binding.saved,
    }
    if binding.title is not None:
        body["title"] = binding.title
    if binding.confirmation_url is not None:
        body["confirmation"] = {"type": "redirect", "confirmation_url": binding.confirmation_url}
    return body


def create_yookassa_app() -> Starlette:
    """Собирает HTTP-границу заглушки; compose не выпускает её за loopback."""
    fake = FakeYooKassa()

    async def create(request: Request) -> Response:
        try:
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("amount"), dict):
                raise ValueError
            amount = Decimal(str(body["amount"]["value"]))
            currency = str(body["amount"]["currency"])
            key = request.headers["idempotence-key"]
            is_replay = key in fake._keys
            confirmation = body.get("confirmation")
            return_url = (
                str(confirmation.get("return_url"))
                if isinstance(confirmation, dict) and confirmation.get("return_url") is not None
                else "http://localhost/renewal"
            )
            payment = await fake.create_payment(
                idempotence_key=key,
                amount_rub=amount,
                return_url=return_url,
                description=str(body.get("description", "")),
                save_payment_method=body.get("save_payment_method") is True,
                payment_method_id=(
                    str(body["payment_method_id"])
                    if body.get("payment_method_id") is not None
                    else None
                ),
            )
            # Повтор у провайдера возвращает исходный снимок. Первый запрос
            # вправе создать платёж не в рублях, но повтор с тем же ключом
            # не должен переписать уже сохранённый платёж.
            if not is_replay and currency != payment.currency:
                payment = replace(payment, currency=currency)
                fake._payments[payment.id] = payment
            return JSONResponse(_payment_json(payment), status_code=200)
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return JSONResponse({"description": "invalid payment request"}, status_code=400)

    async def get(request: Request) -> Response:
        payment_id = request.path_params["payment_id"]
        try:
            return JSONResponse(_payment_json(await fake.get_payment(payment_id)))
        except KeyError:
            return JSONResponse({"description": "payment not found"}, status_code=404)

    async def status(request: Request) -> Response:
        try:
            payload: Any = await request.json()
            if not isinstance(payload, dict):
                raise ValueError
            status_value = YooKassaPaymentStatus(str(payload["status"]))
            await fake.set_status(request.path_params["payment_id"], status_value)
            return Response(status_code=204)
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"description": "invalid status"}, status_code=400)

    async def latest(_: Request) -> Response:
        payment_id = fake.latest_payment_id()
        if payment_id is None:
            return JSONResponse({"description": "payment not found"}, status_code=404)
        return JSONResponse({"id": payment_id})

    async def pause(_: Request) -> Response:
        fake.pause_gets()
        return Response(status_code=204)

    async def release(_: Request) -> Response:
        fake.release_gets()
        return Response(status_code=204)

    async def create_binding(request: Request) -> Response:
        try:
            body = await request.json()
            if not isinstance(body, dict) or body.get("type") != "bank_card":
                raise ValueError
            confirmation = body.get("confirmation")
            if not isinstance(confirmation, dict) or confirmation.get("return_url") is None:
                raise ValueError
            binding = await fake.create_card_binding(
                idempotence_key=request.headers["idempotence-key"],
                return_url=str(confirmation["return_url"]),
            )
            return JSONResponse(_binding_json(binding), status_code=200)
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"description": "invalid binding request"}, status_code=400)

    async def get_binding(request: Request) -> Response:
        try:
            return JSONResponse(
                _binding_json(await fake.get_card_binding(request.path_params["binding_id"]))
            )
        except KeyError:
            return JSONResponse({"description": "payment method not found"}, status_code=404)

    async def binding_status(request: Request) -> Response:
        try:
            payload: Any = await request.json()
            if not isinstance(payload, dict):
                raise ValueError
            await fake.set_binding(
                request.path_params["binding_id"],
                status=YooKassaBindingStatus(str(payload["status"])),
                saved=payload.get("saved") is True,
            )
            return Response(status_code=204)
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"description": "invalid binding status"}, status_code=400)

    async def save_next_card(request: Request) -> Response:
        """Стенд заранее выбирает, отметит ли плательщик «запомнить карту»."""
        payload: Any = await request.json()
        fake.save_next_card = isinstance(payload, dict) and payload.get("saved") is True
        return Response(status_code=204)

    app = Starlette(
        routes=[
            Route("/health", lambda _: JSONResponse({"status": "ok"}), methods=["GET"]),
            Route("/v3/payments", create, methods=["POST"]),
            Route("/v3/payments/{payment_id}", get, methods=["GET"]),
            Route("/v3/payment_methods", create_binding, methods=["POST"]),
            Route("/v3/payment_methods/{binding_id}", get_binding, methods=["GET"]),
            Route("/__e2e/bindings/{binding_id}/status", binding_status, methods=["POST"]),
            Route("/__e2e/cards/save-next", save_next_card, methods=["POST"]),
            Route("/__e2e/payments/{payment_id}/status", status, methods=["POST"]),
            Route("/__e2e/payments/latest", latest, methods=["GET"]),
            Route("/__e2e/race/pause-get", pause, methods=["POST"]),
            Route("/__e2e/race/release-get", release, methods=["POST"]),
        ]
    )
    app.state.yookassa = fake
    return app


yookassa_app = create_yookassa_app()

__all__ = ["FakeYooKassa", "create_yookassa_app", "yookassa_app"]
