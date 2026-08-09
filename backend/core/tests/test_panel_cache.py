"""Кэш ответов панели: срок жизни, гашение, устойчивость к мусору."""

from __future__ import annotations

from datetime import date

from fakeredis.aioredis import FakeRedis

from repibot_core.services.panel_cache import PanelCache, devices_key, usage_key


async def test_value_survives_round_trip() -> None:
    cache = PanelCache(FakeRedis(), ttl_seconds=60)
    await cache.put("ключ", [{"hwid": "hwid-1", "platform": None}])

    assert await cache.get("ключ") == [{"hwid": "hwid-1", "platform": None}]


async def test_missing_key_is_none() -> None:
    assert await PanelCache(FakeRedis(), ttl_seconds=60).get("нет-такого") is None


async def test_drop_removes_value() -> None:
    """Отвязка устройства гасит кэш сразу, не дожидаясь истечения срока."""
    cache = PanelCache(FakeRedis(), ttl_seconds=60)
    await cache.put("ключ", [1])
    await cache.drop("ключ")

    assert await cache.get("ключ") is None


async def test_broken_value_is_treated_as_missing() -> None:
    """В кэше копия того, что и так перезапрашивается: падать из-за неё незачем."""
    redis = FakeRedis()
    await redis.set("ключ", "не json")

    assert await PanelCache(redis, ttl_seconds=60).get("ключ") is None


async def test_ttl_is_set() -> None:
    """Без срока жизни значение осталось бы в Valkey навсегда."""
    redis = FakeRedis()
    await PanelCache(redis, ttl_seconds=60).put("ключ", [1])

    assert 0 < await redis.ttl("ключ") <= 60


def test_keys_are_distinct_per_user_and_period() -> None:
    assert devices_key(1) != devices_key(2)
    assert usage_key(1, date(2026, 8, 1), date(2026, 8, 6)) != usage_key(
        1, date(2026, 7, 1), date(2026, 8, 6)
    )
