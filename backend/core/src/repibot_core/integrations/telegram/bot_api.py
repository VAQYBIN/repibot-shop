"""Обращения к Bot API вне процесса бота.

Нужен ровно один вызов — getMe: без имени бота нельзя собрать ссылку
`t.me/<bot>?start=link_XXX`. Имя меняется редко, поэтому ответ кэшируется.
"""

from __future__ import annotations

import httpx
from redis.asyncio import Redis

from repibot_core.services.auth.types import AuthError
from repibot_core.settings import Settings

CACHE_KEY = "telegram:bot:username"
CACHE_TTL_SECONDS = 86_400
TIMEOUT_SECONDS = 10.0


class BotApi:
    def __init__(
        self, settings: Settings, redis: Redis, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    async def username(self) -> str:
        # Клиент создаётся с `decode_responses=False`, поэтому из кэша приходят
        # `bytes`; строка допускается на случай клиента с декодированием.
        cached: object = await self._redis.get(CACHE_KEY)
        if isinstance(cached, bytes):
            return cached.decode()
        if cached is not None:
            return str(cached)

        token = self._settings.bot_token.get_secret_value()
        try:
            # Токен в пути — требование Bot API. В журнал этот адрес не пишется.
            response = await self._client.get(f"https://api.telegram.org/bot{token}/getMe")
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AuthError("telegram_unavailable", "Telegram не ответил на getMe") from error

        name = response.json().get("result", {}).get("username")
        if not isinstance(name, str) or not name:
            raise AuthError("telegram_unavailable", "Bot API не вернул имя бота")

        await self._redis.set(CACHE_KEY, name, ex=CACHE_TTL_SECONDS)
        return name
