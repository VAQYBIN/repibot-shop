"""Одноразовые challenge WebAuthn в Valkey.

Challenge выдаётся сервером и должен приниматься ровно один раз: иначе
записанный ответ аутентификатора можно предъявить повторно. Ключ гасится тем
же запросом, которым читается, — GETDEL не оставляет окна между проверкой и
удалением.
"""

from __future__ import annotations

from redis.asyncio import Redis
from webauthn.helpers import bytes_to_base64url

# Пять минут: столько живёт системное окно выбора ключа, дольше challenge не
# нужен, а короче — не хватит человеку с аппаратным ключом в кармане.
CHALLENGE_TTL_SECONDS = 300


class ChallengeStore:
    def __init__(self, redis: Redis, ttl_seconds: int = CHALLENGE_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(purpose: str, challenge: bytes) -> str:
        return f"webauthn:{purpose}:{bytes_to_base64url(challenge)}"

    async def remember(self, purpose: str, challenge: bytes, *, user_id: int | None = None) -> None:
        """Запоминает challenge. Пустое значение означает вход без известного пользователя."""
        value = "" if user_id is None else str(user_id)
        await self._redis.set(self._key(purpose, challenge), value, ex=self._ttl)

    async def take(self, purpose: str, challenge: bytes) -> str | None:
        """Забирает challenge. None — такого не выдавали или его уже использовали.

        Клиент создаётся с `decode_responses=False`, поэтому GETDEL возвращает
        `bytes`; строка на входе допускается на случай клиента с декодированием.
        """
        stored: object = await self._redis.getdel(self._key(purpose, challenge))
        if stored is None:
            return None
        if isinstance(stored, bytes):
            return stored.decode()
        return str(stored)
