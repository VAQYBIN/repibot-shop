"""Единый формат ошибок API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from repibot_core.logging import request_id_var

logger = logging.getLogger(__name__)

HEADER = "X-Request-ID"

# Коды для ответов, которые порождает не наш код, а фреймворк.
_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    429: "too_many_requests",
}


class ApiError(Exception):
    """Ожидаемая ошибка, о которой клиенту можно рассказать честно."""

    def __init__(self, message: str, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Собирает ответ в общем формате.

    Идентификатор запроса ставится здесь, а не в middleware: ответ 500
    собирает ServerErrorMiddleware, а он стоит снаружи пользовательских
    middleware, и обратно через них ответ уже не проходит.
    """
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details

    headers = {}
    request_id = request_id_var.get()
    if request_id is not None:
        headers[HEADER] = request_id

    return JSONResponse(status_code=status_code, content={"error": body}, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Сведения по полям сохраняются: без них форма не покажет, что неверно.
        # Поле input выброшено — в нём лежит то, что прислал клиент, вплоть
        # до пароля из формы входа.
        details = [
            {"loc": [str(part) for part in error["loc"]], "msg": error["msg"]}
            for error in exc.errors()
        ]
        return _error_response(422, "validation_error", "Проверьте введённые данные", details)

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("необработанная ошибка", exc_info=exc)
        return _error_response(500, "internal_error", "Внутренняя ошибка")
