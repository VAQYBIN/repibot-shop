"""Cookie входа: refresh-сессия и привязка начатого входа через Telegram."""

from __future__ import annotations

from datetime import datetime

from fastapi import Response

REFRESH_COOKIE = "repibot_refresh"
# Путь ограничен единственным потребителем: браузер не пошлёт cookie ни на один
# другой эндпоинт, и поверхность CSRF сводится к одному методу.
COOKIE_PATH = "/api/auth/refresh"

OIDC_COOKIE = "repibot_oidc"
OIDC_COOKIE_PATH = "/api/auth/telegram"
# Столько же, сколько живёт state в Valkey: cookie и запись — две половины
# одной попытки входа, и переживать друг друга им незачем.
OIDC_COOKIE_MAX_AGE = 600


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


def set_oidc_cookie(response: Response, binding: str, *, secure: bool) -> None:
    """Привязывает начатый вход через Telegram к этому браузеру.

    Без неё вход уязвим к подделке: злоумышленник начинает вход у себя, получает
    рабочий код и подсовывает жертве ссылку возврата. Жертва оказывается в чужом
    аккаунте, не заметив подмены, и дальше платит за чужую подписку.

    SameSite=lax обязателен именно такой: возврат с oauth.telegram.org — это
    межсайтовый переход, и при `strict` cookie бы не отправилась вовсе.
    """
    response.set_cookie(
        OIDC_COOKIE,
        binding,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=OIDC_COOKIE_PATH,
        max_age=OIDC_COOKIE_MAX_AGE,
    )


def clear_oidc_cookie(response: Response, *, secure: bool) -> None:
    response.set_cookie(
        OIDC_COOKIE,
        "",
        httponly=True,
        secure=secure,
        samesite="lax",
        path=OIDC_COOKIE_PATH,
        max_age=0,
    )
