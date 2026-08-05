"""Сквозной идентификатор запроса."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from repibot_core.logging import request_id_var

HEADER = "X-Request-ID"


def request_id_of(request: Request) -> str | None:
    """Идентификатор текущего запроса.

    Читается из состояния запроса, а не из контекстной переменной: обработчик
    ошибки 500 вызывается снаружи этого middleware, когда переменная уже сброшена.
    """
    return getattr(request.state, "request_id", None)


def register_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        # Через токен и reset: без сброса значение переживает запрос и достаётся
        # всему, что выполняется в том же контексте после ответа.
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers[HEADER] = request_id
        return response
