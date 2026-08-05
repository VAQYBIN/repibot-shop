"""Разбор очереди: ретраи, отказы, повторная обработка."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.services.outbox import MAX_ATTEMPTS, RETRY_DELAYS, OutboxDispatcher

pytestmark = pytest.mark.docker


async def test_handler_is_called_and_message_marked(db_session: AsyncSession) -> None:
    calls: list[dict[str, object]] = []
    dispatcher = OutboxDispatcher()

    async def collect(payload: dict[str, object]) -> None:
        calls.append(payload)

    dispatcher.register("test.topic", collect)

    await OutboxRepository(db_session).add("test.topic", {"value": 1})
    await db_session.commit()

    processed = await dispatcher.process(db_session)

    assert processed == 1
    assert calls == [{"value": 1}]
    assert await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC)) == []


async def test_failed_handler_postpones_with_growing_delay(db_session: AsyncSession) -> None:
    dispatcher = OutboxDispatcher()

    async def failing(payload: dict[str, object]) -> None:
        raise RuntimeError("SMTP недоступен")

    dispatcher.register("test.topic", failing)
    message = await OutboxRepository(db_session).add("test.topic", {})
    await db_session.commit()

    await dispatcher.process(db_session)

    assert message.attempts == 1
    assert message.processed_at is None
    assert message.last_error is not None
    assert message.available_at > datetime.now(UTC)


async def test_message_is_dropped_after_max_attempts(db_session: AsyncSession) -> None:
    """Бесконечно ретраить нельзя: очередь перестанет разбираться вовсе."""
    dispatcher = OutboxDispatcher()

    async def failing(payload: dict[str, object]) -> None:
        raise RuntimeError("адрес не существует")

    dispatcher.register("test.topic", failing)
    message = await OutboxRepository(db_session).add("test.topic", {})
    message.attempts = MAX_ATTEMPTS - 1
    await db_session.commit()

    await dispatcher.process(db_session)

    assert message.processed_at is not None
    assert message.last_error is not None


async def test_unknown_topic_is_postponed_not_lost(db_session: AsyncSession) -> None:
    """Незнакомая тема — это выкат новой версии в момент работы старого воркера."""
    dispatcher = OutboxDispatcher()
    message = await OutboxRepository(db_session).add("unknown.topic", {})
    await db_session.commit()

    await dispatcher.process(db_session)

    assert message.processed_at is None
    assert message.attempts == 1


def test_retry_delays_grow() -> None:
    assert RETRY_DELAYS[0] < RETRY_DELAYS[-1]
    assert len(RETRY_DELAYS) == MAX_ATTEMPTS
    assert RETRY_DELAYS[0] == timedelta(seconds=10)
