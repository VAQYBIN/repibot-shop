"""Deterministic YooKassa substitute used only by the isolated E2E compose stack."""

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

from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus


class FakeYooKassa:
    """In-memory provider truth with a deliberate callback-versus-poll seam."""

    def __init__(self) -> None:
        self._payments: dict[str, YooKassaPayment] = {}
        self._keys: dict[str, str] = {}
        self._ids = count(1)
        self._latest_payment_id: str | None = None
        self._get_gate = asyncio.Event()
        self._get_gate.set()
        self._get_started = asyncio.Event()

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
        """Mirror YooKassa idempotence and return only normalized provider fields."""
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
        )
        self._keys[idempotence_key] = payment_id
        self._payments[payment_id] = payment
        self._latest_payment_id = payment_id
        return payment

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
        body["payment_method"] = {"id": payment.payment_method_id}
    return body


def create_yookassa_app() -> Starlette:
    """Create the fake HTTP boundary; compose does not publish it beyond loopback."""
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
            # A provider replay returns the original commercial snapshot.  A
            # request can choose a non-RUB fake payment on first create, but
            # its same-key replay must never rewrite that stored payment.
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

    app = Starlette(
        routes=[
            Route("/health", lambda _: JSONResponse({"status": "ok"}), methods=["GET"]),
            Route("/v3/payments", create, methods=["POST"]),
            Route("/v3/payments/{payment_id}", get, methods=["GET"]),
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
