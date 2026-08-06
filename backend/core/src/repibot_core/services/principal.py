"""Кто выполняет запрос: роль, статус, язык.

Роль не лежит в access-токене — иначе блокировка пользователя начинала бы
действовать через время жизни токена. Вместо этого одно чтение из Valkey с
коротким сроком жизни, с проваливанием в базу при промахе.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import UserRole, UserStatus
from repibot_core.db.repositories.users import UserRepository

PRINCIPAL_TTL_SECONDS = 30


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    role: UserRole
    status: UserStatus
    language: str

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.active


class PrincipalCache:
    def __init__(self, redis: Redis, ttl_seconds: int = PRINCIPAL_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(user_id: int) -> str:
        return f"principal:{user_id}"

    @staticmethod
    def _revoked_key(session_id: UUID) -> str:
        return f"session:revoked:{session_id}"

    async def get(self, session: AsyncSession, user_id: int) -> Principal | None:
        cached = await self._redis.get(self._key(user_id))
        if cached is not None:
            data = json.loads(cached)
            return Principal(
                user_id=data["user_id"],
                role=UserRole(data["role"]),
                status=UserStatus(data["status"]),
                language=data["language"],
            )

        user = await UserRepository(session).get(user_id)
        if user is None:
            return None

        principal = Principal(
            user_id=user.id, role=user.role, status=user.status, language=user.language
        )
        await self._redis.set(
            self._key(user_id),
            json.dumps(
                {
                    "user_id": principal.user_id,
                    "role": principal.role.value,
                    "status": principal.status.value,
                    "language": principal.language,
                }
            ),
            ex=self._ttl,
        )
        return principal

    async def invalidate(self, user_id: int) -> None:
        await self._redis.delete(self._key(user_id))

    async def mark_session_revoked(self, session_id: UUID, *, ttl_seconds: int) -> None:
        """Помечает сессию отозванной на время жизни выданного access-токена.

        Дольше держать незачем: после истечения токена он не примется и без
        отметки. Без отметки же отзыв сессии подействовал бы только к тому же
        моменту — а критерий приёмки требует немедленности.
        """
        await self._redis.set(self._revoked_key(session_id), "1", ex=ttl_seconds)

    async def is_session_revoked(self, session_id: UUID) -> bool:
        return await self._redis.exists(self._revoked_key(session_id)) == 1
