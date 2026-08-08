"""Приём событий панели: подпись, дедупликация, реакции."""

from __future__ import annotations

import hashlib
import hmac
import json
from asyncio import Barrier, create_task, gather, sleep
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import (
    OutboxMessage,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
    WebhookEvent,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.panel_cache import PanelCache, devices_key
from repibot_core.services.panel_webhooks import PanelWebhookService, verify_signature
from repibot_core.services.provisioning import TOPIC_PROVISION

# Метка docker стоит на тестах с базой поимённо, а не на модуле: проверки
# подписи — чистая арифметика, и отнимать у них возможность прогона без
# контейнера незачем.
docker = pytest.mark.docker

SECRET = "секрет-панели"


def _signed(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_signature_is_checked_over_raw_body() -> None:
    body = json.dumps({"scope": "user"}, ensure_ascii=False).encode()
    assert verify_signature(SECRET, body, _signed(body)) is True
    assert verify_signature(SECRET, body, _signed("другое".encode())) is False
    assert verify_signature(SECRET, body, None) is False


def test_empty_secret_never_verifies() -> None:
    """Пустой секрет означает «вебхуки не настроены», а не «принимай всё»."""
    body = b"{}"
    assert verify_signature("", body, hmac.new(b"", body, hashlib.sha256).hexdigest()) is False


def test_signature_survives_prefix_and_spaces() -> None:
    """Панель может прислать подпись с префиксом схемы — это та же подпись."""
    body = b'{"scope":"user"}'
    assert verify_signature(SECRET, body, f" sha256={_signed(body)} ") is True


async def _subscriber(db_session: AsyncSession) -> User:
    plan = await PlanRepository(db_session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="w@example.org", referral_code="whk00001", remnawave_id=42)
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await db_session.commit()
    return user


def _event(event: str, *, scope: str = "user", panel_id: int = 42) -> dict[str, object]:
    data: dict[str, object] = (
        {"id": panel_id} if scope == "user" else {"user": {"id": panel_id}, "device": {}}
    )
    return {
        "scope": scope,
        "event": event,
        "timestamp": "2026-08-06T12:00:00Z",
        "data": data,
    }


@docker
async def test_repeated_delivery_is_ignored(db_session: AsyncSession) -> None:
    await _subscriber(db_session)
    service = PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60))

    assert await service.handle(_event("user.revoked")) is True
    assert await service.handle(_event("user.revoked")) is False


@docker
async def test_concurrent_delivery_is_stored_and_processed_once(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Одинаковые доставки на разных соединениях не ломают приём вебхука."""
    await _subscriber(db_session)
    factory = create_session_factory(engine)
    ready = Barrier(2)

    async def deliver() -> bool:
        async with factory() as session:
            await ready.wait()
            return await PanelWebhookService(
                session, PanelCache(FakeRedis(), ttl_seconds=60)
            ).handle(_event("user.revoked"))

    async with factory() as lock_session:
        # SHARE ROW EXCLUSIVE не мешает SELECT из старого алгоритма, но держит
        # оба его INSERT. Поэтому к моменту снятия lock обе сессии уже увидели
        # отсутствие события и воспроизводят реальную гонку без mock'ов.
        await lock_session.execute(text("LOCK TABLE webhook_events IN SHARE ROW EXCLUSIVE MODE"))
        deliveries = [create_task(deliver()) for _ in range(2)]
        try:
            for _ in range(500):
                waiting = await lock_session.scalar(
                    text(
                        "SELECT count(*) FROM pg_locks "
                        "WHERE relation = 'webhook_events'::regclass AND NOT granted"
                    )
                )
                if waiting == 2:
                    break
                await sleep(0.01)
            else:
                raise AssertionError("доставки не дошли до конфликтующих INSERT")
        finally:
            await lock_session.rollback()

    outcomes = await gather(*deliveries)

    assert sorted(outcomes) == [False, True]
    async with factory() as session:
        events = (await session.execute(select(WebhookEvent))).scalars().all()
        messages = (await session.execute(select(OutboxMessage))).scalars().all()
    assert len(events) == 1
    assert events[0].processed_at is not None
    assert [message.topic for message in messages] == [TOPIC_PROVISION]


@docker
async def test_state_event_queues_reconcile(db_session: AsyncSession) -> None:
    """Панель изменили мимо нас — надо привести её обратно к нашему состоянию."""
    await _subscriber(db_session)
    service = PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60))

    await service.handle(_event("user.revoked"))

    queued = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert [message.topic for message in queued] == [TOPIC_PROVISION]


@docker
async def test_device_event_drops_cache(db_session: AsyncSession) -> None:
    user = await _subscriber(db_session)
    redis = FakeRedis()
    cache = PanelCache(redis, ttl_seconds=60)
    await cache.put(devices_key(user.id), [{"hwid": "старое"}])

    await PanelWebhookService(db_session, cache).handle(
        _event("user_hwid_devices.added", scope="user_hwid_devices")
    )

    assert await cache.get(devices_key(user.id)) is None


@docker
async def test_expiry_event_does_not_move_our_date(db_session: AsyncSession) -> None:
    """Вебхук — повод посмотреть, а не источник биллинга."""
    user = await _subscriber(db_session)
    before = await SubscriptionRepository(db_session).get_for_user(user.id)
    assert before is not None
    expires_at = before.expires_at

    await PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60)).handle(
        _event("user.expired")
    )

    await db_session.refresh(before)
    assert before.expires_at == expires_at


@docker
async def test_unknown_event_is_stored_and_ignored(db_session: AsyncSession) -> None:
    """Панель обновится раньше нас; незнакомое событие не должно валить приём."""
    await _subscriber(db_session)
    service = PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60))

    assert await service.handle(_event("user.какое-то-новое")) is True
    queued = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert queued == []


@docker
async def test_foreign_panel_user_is_stored_without_reaction(db_session: AsyncSession) -> None:
    """Пользователь панели, заведённый мимо нас, трогать себя не даёт."""
    await _subscriber(db_session)
    service = PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60))

    assert await service.handle(_event("user.revoked", panel_id=777)) is True

    queued = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert queued == []
