"""Единый формат ошибок API."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Ожидаемая ошибка, о которой клиенту можно рассказать честно."""

    def __init__(self, message: str, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message))

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("необработанная ошибка", exc_info=exc)
        return JSONResponse(status_code=500, content=_body("internal_error", "Внутренняя ошибка"))
