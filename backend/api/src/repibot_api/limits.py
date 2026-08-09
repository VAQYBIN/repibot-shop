"""Общее ограничение частоты для маршрутов API."""

from __future__ import annotations

from datetime import timedelta

from fastapi import status
from redis.asyncio import Redis

from repibot_api.errors import ApiError
from repibot_core.ratelimit import RateLimiter, Rule

# Оплата создаёт запись в нашей БД и запрос в стороннем провайдере. Пять
# попыток за минуту покрывают повтор после сетевой ошибки, но не бесконечный
# кликер формы; правило применяется и к user, и к IP.
PAYMENT_CREATE = Rule(limit=5, window=timedelta(minutes=1))


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
