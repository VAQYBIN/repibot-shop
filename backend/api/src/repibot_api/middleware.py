"""Сквозной идентификатор запроса."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from repibot_core.logging import set_request_id

HEADER = "X-Request-ID"


def register_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_id(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(HEADER) or str(uuid.uuid4())
        set_request_id(request_id)
        response = await call_next(request)
        response.headers[HEADER] = request_id
        return response
