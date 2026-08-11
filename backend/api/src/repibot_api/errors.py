"""Единый формат ошибок API."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from repibot_api.middleware import HEADER, request_id_of
from repibot_core.services.auth.types import AuthError
from repibot_core.services.errors import ServiceError

logger = logging.getLogger(__name__)

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

    def __init__(
        self,
        message: str,
        status_code: int,
        code: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        # Retry-After для 429: без него клиент не знает, когда повторить, и
        # повторяет немедленно.
        self.headers = headers or {}


# Статус выбирается здесь, а не в сервисе: сервис знает, что произошло, а не
# как об этом принято сообщать по HTTP.
_AUTH_STATUS = {
    "invalid_credentials": 401,
    "unauthorized": 401,
    "email_not_verified": 403,
    "forbidden": 403,
    "not_found": 404,
    "email_taken": 409,
    # Конфликт состояния, а не ошибка запроса: тот же запрос при другом
    # состоянии аккаунта пройдёт.
    "last_login_method": 409,
    "telegram_already_linked": 409,
    "link_conflict": 409,
    "token_invalid": 400,
    "weak_password": 422,
    "validation_error": 422,
    "rate_limited": 429,
    # Не наша поломка, а недоступность Telegram: человеку нужно повторить
    # позже, а не искать ошибку у себя.
    "telegram_unavailable": 503,
}


def api_error_from(error: AuthError) -> ApiError:
    return ApiError(str(error), _AUTH_STATUS.get(error.code, 400), error.code)


# Ошибки предметных сервисов переводятся в HTTP по тому же правилу, что и
# ошибки входа: код называет событие, статус выбирает слой API.
_SERVICE_STATUS = {
    "not_found": 404,
    "plan_not_found": 404,
    "plan_inactive": 409,
    "order_expired": 409,
    "order_not_found": 404,
    "refund_invalid": 409,
    "compensation_invalid": 409,
    "compensation_already_applied": 409,
    "reward_missing": 404,
    "promo_unavailable": 409,
    "gift_unavailable": 409,
    "provider_unavailable": 503,
    "plan_code_taken": 409,
    "plan_squads_unknown": 422,
    "subscription_missing": 404,
    "subscription_not_found": 409,
    "auto_renew_unavailable": 409,
    "binding_unavailable": 409,
    "subscription_exists": 409,
    "trial_already_used": 409,
    "trial_requires_telegram": 409,
    "trial_disabled": 409,
    "device_not_found": 404,
    # Поддержки на стенде может не быть вовсе. Это состояние развёртывания, а
    # не ошибка запроса: тот же запрос на стенде с супергруппой пройдёт.
    "support_unavailable": 409,
    "too_many_tickets": 409,
    "ticket_closed": 409,
    "broadcast_not_draft": 409,
    "broadcast_busy": 409,
    "broadcast_not_running": 409,
    # Имя сегмента и тексты кампании — значения, которые прислал клиент.
    "unknown_segment": 422,
    "broadcast_text_required": 422,
    # Ссылка отписки испорчена или не наша: ошибка запроса, а не отказ доступа.
    # 401 и 403 увели бы человека без сессии на форму входа.
    "invalid_token": 400,
    # Не наша поломка, а недоступность панели: человеку нужно повторить
    # позже, а не искать ошибку у себя.
    "panel_unavailable": 503,
}


def api_error_from_service(error: ServiceError) -> ApiError:
    return ApiError(str(error), _SERVICE_STATUS.get(error.code, 400), error.code)


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Собирает ответ в общем формате.

    Идентификатор запроса ставится здесь, а не в middleware: ответ 500
    собирает ServerErrorMiddleware, а он стоит снаружи пользовательских
    middleware, и обратно через них ответ уже не проходит.
    """
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details

    headers = dict(extra_headers or {})
    request_id = request_id_of(request)
    if request_id is not None:
        headers[HEADER] = request_id

    return JSONResponse(status_code=status_code, content={"error": body}, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(
            request, exc.status_code, exc.code, exc.message, extra_headers=exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        return _error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Сведения по полям сохраняются: без них форма не покажет, что неверно.
        # Поле input выброшено — в нём лежит то, что прислал клиент, вплоть
        # до пароля из формы входа.
        details = [
            {"loc": [str(part) for part in error["loc"]], "msg": error["msg"]}
            for error in exc.errors()
        ]
        return _error_response(
            request, 422, "validation_error", "Проверьте введённые данные", details
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Идентификатор передаётся явно: контекстная переменная к этому моменту
        # уже сброшена, обработчик вызывается снаружи middleware.
        logger.exception(
            "необработанная ошибка", exc_info=exc, extra={"request_id": request_id_of(request)}
        )
        return _error_response(request, 500, "internal_error", "Внутренняя ошибка")
