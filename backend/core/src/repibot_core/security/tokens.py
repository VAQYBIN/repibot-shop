"""Токены: короткий подписанный access и непрозрачный refresh.

В access-токене только идентификатор пользователя и идентификатор сессии.
Роли в нём нет намеренно: она читается из базы через кэш, иначе блокировка
пользователя начинала бы действовать через время жизни токена.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

ALGORITHM = "HS256"
OPAQUE_TOKEN_BYTES = 32


class TokenInvalidError(Exception):
    """Токен просрочен, подделан или не разбирается."""


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: int
    session_id: UUID


def create_access_token(
    user_id: int,
    session_id: UUID,
    *,
    secret: str,
    ttl_minutes: int,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> AccessClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return AccessClaims(user_id=int(payload["sub"]), session_id=UUID(payload["sid"]))
    except (jwt.PyJWTError, KeyError, ValueError) as error:
        raise TokenInvalidError(str(error)) from error


def generate_opaque_token() -> str:
    """Refresh-токен и одноразовые токены из писем.

    Непрозрачный, а не подписанный: такой токен отзывается вычёркиванием из
    базы, а подписанный живёт до истечения срока независимо от нашего желания.
    """
    return secrets.token_urlsafe(OPAQUE_TOKEN_BYTES)


def hash_opaque_token(raw: str) -> str:
    """SHA-256 без соли.

    Соль здесь не нужна и вредна: токен — 256 бит случайности, перебор
    невозможен, а поиск по базе должен идти по индексу одним запросом.
    """
    return hashlib.sha256(raw.encode()).hexdigest()
