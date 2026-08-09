"""Ограничение частоты запросов.

Скользящее окно на sorted set: каждая попытка — элемент с отметкой времени,
старые вычищаются перед подсчётом. Фиксированное окно дало бы двойной лимит на
стыке периодов, а именно стык и выбирают для перебора.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class Rule:
    limit: int
    window: timedelta


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


LOGIN_PER_IP = Rule(limit=10, window=timedelta(minutes=1))
LOGIN_PER_EMAIL = Rule(limit=5, window=timedelta(minutes=1))
REGISTER_PER_IP = Rule(limit=5, window=timedelta(hours=1))
LETTER_PER_EMAIL = Rule(limit=3, window=timedelta(hours=1))
LETTER_PER_IP = Rule(limit=10, window=timedelta(hours=1))
MINIAPP_PER_IP = Rule(limit=30, window=timedelta(minutes=1))
# Выдача параметров passkey дешева для нас и бесполезна для перебора, но
# бесконечной быть не должна: challenge занимает место в Valkey.
PASSKEY_PER_IP = Rule(limit=20, window=timedelta(minutes=1))
# Старт входа через Telegram — тот же случай: аноним без ограничения набивает
# память записями state, каждая из которых живёт десять минут.
OIDC_START_PER_IP = Rule(limit=20, window=timedelta(minutes=1))
# Код привязки виден в чате бота: пять штук в час хватает любому нормальному
# сценарию и отсекает попытку набить Valkey кодами.
LINK_CODE_PER_USER = Rule(limit=5, window=timedelta(hours=1))
# Отвязка устройства защищает не нас, а панель: без ограничения скрипт крутит
# отвязку в цикле и обходит лимит устройств тарифа. Значение берётся из
# настроек, поэтому правило собирается на месте вызова, а не объявляется здесь
# константой.
DEVICE_UNLINK_WINDOW = timedelta(days=1)


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, rule: Rule, *, now: datetime | None = None) -> RateLimitResult:
        moment = now or datetime.now(UTC)
        timestamp = moment.timestamp()
        cutoff = timestamp - rule.window.total_seconds()
        full_key = f"ratelimit:{key}"

        pipeline = self._redis.pipeline()
        pipeline.zremrangebyscore(full_key, 0, cutoff)
        # Член множества уникален: две попытки в одну миллисекунду должны
        # считаться двумя.
        pipeline.zadd(full_key, {f"{timestamp}:{uuid4()}": timestamp})
        pipeline.zcard(full_key)
        pipeline.expire(full_key, int(rule.window.total_seconds()) + 1)
        results = await pipeline.execute()

        count = int(results[2])
        if count <= rule.limit:
            return RateLimitResult(allowed=True, retry_after_seconds=0)

        oldest = await self._redis.zrange(full_key, 0, 0, withscores=True)
        retry_after = rule.window.total_seconds()
        if oldest:
            retry_after = float(oldest[0][1]) + rule.window.total_seconds() - timestamp
        return RateLimitResult(allowed=False, retry_after_seconds=max(1, math.ceil(retry_after)))
