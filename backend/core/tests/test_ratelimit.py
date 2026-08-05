"""Скользящее окно на Valkey."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fakeredis.aioredis import FakeRedis

from repibot_core.ratelimit import (
    LOGIN_PER_EMAIL,
    LOGIN_PER_IP,
    RateLimiter,
    Rule,
)

RULE = Rule(limit=3, window=timedelta(minutes=1))


async def test_requests_under_limit_are_allowed() -> None:
    limiter = RateLimiter(FakeRedis())

    for _ in range(3):
        assert (await limiter.hit("k", RULE)).allowed is True


async def test_request_over_limit_is_refused_with_retry_after() -> None:
    limiter = RateLimiter(FakeRedis())
    for _ in range(3):
        await limiter.hit("k", RULE)

    result = await limiter.hit("k", RULE)

    assert result.allowed is False
    assert 0 < result.retry_after_seconds <= 60


async def test_window_slides() -> None:
    """Окно скользящее: через минуту после первых попыток счёт обнуляется."""
    limiter = RateLimiter(FakeRedis())
    start = datetime.now(UTC)
    for _ in range(3):
        await limiter.hit("k", RULE, now=start)

    later = await limiter.hit("k", RULE, now=start + timedelta(seconds=61))

    assert later.allowed is True


async def test_keys_are_independent() -> None:
    limiter = RateLimiter(FakeRedis())
    for _ in range(3):
        await limiter.hit("first", RULE)

    assert (await limiter.hit("second", RULE)).allowed is True


def test_rules_match_the_spec() -> None:
    assert Rule(limit=10, window=timedelta(minutes=1)) == LOGIN_PER_IP
    assert Rule(limit=5, window=timedelta(minutes=1)) == LOGIN_PER_EMAIL
