"""Кэш ответов панели.

Трафик и устройства принадлежат панели, а не нам, и дублировать их у себя
нельзя: наша копия устаревала бы с каждым подключением клиента. Но экран
кабинета опрашивают часто, а меняются эти данные редко — минуты хватает,
чтобы снять с панели поток одинаковых запросов и не показать вчерашнее.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from redis.asyncio import Redis


class PanelCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def get(self, key: str) -> Any | None:
        """Разобранное значение или None, если его нет.

        Битое значение считается отсутствующим: в кэше лежит копия того, что
        и так можно перезапросить, и падать из-за неё — терять экран на ровном
        месте.
        """
        stored: object = await self._redis.get(key)
        if stored is None:
            return None
        raw = stored.decode() if isinstance(stored, bytes) else str(stored)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def put(self, key: str, value: Any) -> None:
        await self._redis.set(key, json.dumps(value, ensure_ascii=False), ex=self._ttl)

    async def drop(self, key: str) -> None:
        await self._redis.delete(key)


def devices_key(user_id: int) -> str:
    return f"panel:devices:{user_id}"


def usage_key(user_id: int, start: date, end: date) -> str:
    """Период входит в ключ: у разных окон разные ответы.

    Без него смена периода на экране отдавала бы данные предыдущего.
    """
    return f"panel:usage:{user_id}:{start.isoformat()}:{end.isoformat()}"
