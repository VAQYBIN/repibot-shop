"""Refresh-cookie. Её видит ровно один эндпоинт."""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

REFRESH_COOKIE = "repibot_refresh"
# Путь ограничен единственным потребителем: браузер не пошлёт cookie ни на один
# другой эндпоинт, и поверхность CSRF сводится к одному методу.
COOKIE_PATH = "/api/auth/refresh"


def set_refresh_cookie(
    response: Response, token: str, *, expires_at: datetime, secure: bool
) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=COOKIE_PATH,
        expires=int(expires_at.timestamp()),
    )


def clear_refresh_cookie(response: Response, *, secure: bool) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        "",
        httponly=True,
        secure=secure,
        samesite="lax",
        path=COOKIE_PATH,
        max_age=0,
    )
