"""Зависимости FastAPI: база, Valkey, текущий пользователь, роли."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from repibot_api.errors import ApiError
from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.db.models import UserRole
from repibot_core.security.tokens import TokenInvalidError, decode_access_token
from repibot_core.services.principal import Principal, PrincipalCache
from repibot_core.settings import Settings, get_settings

# Совпадает с окном проверки живости в health.py: движок там тот же самый.
CONNECT_TIMEOUT_SECONDS = 3.0


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Один движок на процесс: пул соединений создаётся однажды.

    Таймаут подключения короче значения по умолчанию: этим же движком проверяет
    живость `/health`, и ожидание соединения не должно быть длиннее, чем
    отведённое проверке время.
    """
    return create_engine(get_settings().database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS)


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return create_session_factory(get_engine())


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    return Redis.from_url(get_settings().valkey_url, decode_responses=False)


async def db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


def get_principals(redis: Annotated[Redis, Depends(get_redis)]) -> PrincipalCache:
    return PrincipalCache(redis)


def settings_dep() -> Settings:
    return get_settings()


def client_ip(request: Request) -> str | None:
    """Адрес клиента.

    За nginx настоящий адрес приходит в X-Forwarded-For; берётся первый элемент —
    остальные дописаны промежуточными прокси и доверия не заслуживают.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@dataclass(frozen=True, slots=True)
class AuthContext:
    principal: Principal
    session_id: UUID


async def current_context(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    principals: Annotated[PrincipalCache, Depends(get_principals)],
) -> AuthContext:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError("нужен токен доступа", 401, "unauthorized")

    try:
        claims = decode_access_token(
            header.removeprefix("Bearer "), secret=get_settings().jwt_secret.get_secret_value()
        )
    except TokenInvalidError as error:
        raise ApiError("токен недействителен", 401, "unauthorized") from error

    # Отзыв сессии действует немедленно: отметка в Valkey живёт ровно столько,
    # сколько остаётся жить выданному access-токену.
    if await principals.is_session_revoked(claims.session_id):
        raise ApiError("сессия отозвана", 401, "unauthorized")

    principal = await principals.get(session, claims.user_id)
    if principal is None:
        raise ApiError("пользователь не найден", 401, "unauthorized")
    if not principal.is_active:
        raise ApiError("аккаунт заблокирован", 403, "forbidden")

    return AuthContext(principal=principal, session_id=claims.session_id)


def require_role(*roles: UserRole) -> Callable[[AuthContext], AuthContext]:
    """Гейт по роли. Проверка всегда на бэкенде: скрытая кнопка — не защита."""

    def guard(context: Annotated[AuthContext, Depends(current_context)]) -> AuthContext:
        if context.principal.role not in roles:
            raise ApiError("недостаточно прав", 403, "forbidden")
        return context

    return guard
