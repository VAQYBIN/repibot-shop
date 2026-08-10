"""Cookie входа: refresh-сессия и привязка начатого входа через Telegram."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Response

from repibot_core.security.admin_assertion import create_admin_assertion

REFRESH_COOKIE = "repibot_refresh"
# Путь ограничен единственным потребителем: браузер не пошлёт cookie ни на один
# другой эндпоинт, и поверхность CSRF сводится к одному методу.
COOKIE_PATH = "/api/auth/refresh"

OIDC_COOKIE = "repibot_oidc"
OIDC_COOKIE_PATH = "/api/auth/telegram"
# Столько же, сколько живёт state в Valkey: cookie и запись — две половины
# одной попытки входа, и переживать друг друга им незачем.
OIDC_COOKIE_MAX_AGE = 600

# Это признак для маршрутизации в Next.js, а не пропуск в API. Путь не даёт
# ей ездить с обычными запросами и оставляет её видимой только серверному
# гейту /admin.
ADMIN_ASSERTION_COOKIE = "repibot_admin_assertion"
ADMIN_ASSERTION_COOKIE_PATH = "/admin"


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


def set_admin_assertion_cookie(
    response: Response, *, secret: str, ttl_seconds: int, secure: bool
) -> None:
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    response.set_cookie(
        ADMIN_ASSERTION_COOKIE,
        create_admin_assertion(secret, expires_at=expires_at),
        httponly=True,
        secure=secure,
        samesite="lax",
        path=ADMIN_ASSERTION_COOKIE_PATH,
        max_age=ttl_seconds,
        expires=int(expires_at.timestamp()),
    )


def clear_admin_assertion_cookie(response: Response, *, secure: bool) -> None:
    response.set_cookie(
        ADMIN_ASSERTION_COOKIE,
        "",
        httponly=True,
        secure=secure,
        samesite="lax",
        path=ADMIN_ASSERTION_COOKIE_PATH,
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
