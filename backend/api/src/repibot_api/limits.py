"""Общее ограничение частоты для маршрутов API."""

from __future__ import annotations

from fastapi import status
from redis.asyncio import Redis

from repibot_api.errors import ApiError
from repibot_core.ratelimit import RateLimiter, Rule


async def enforce(redis: Redis, key: str, rule: Rule) -> None:
    """Учесть запрос и сообщить клиенту, когда следующая попытка возможна."""
    result = await RateLimiter(redis).hit(key, rule)
    if not result.allowed:
        raise ApiError(
            "слишком часто",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            {"Retry-After": str(result.retry_after_seconds)},
        )
