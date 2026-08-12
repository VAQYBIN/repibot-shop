"""Разбор очереди: ретраи, отказы, повторная обработка."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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


async def test_batch_is_sent_in_parallel_within_the_limit(db_session: AsyncSession) -> None:
    """Последовательная отправка даёт потолок в 1200 сообщений в час.

    Столько же занимает одна рассылка средней базы. Отправки идут
    одновременно, но не больше заданного числа: провайдер не должен получить
    сотню запросов разом.
    """
    repository = OutboxRepository(db_session)
    for index in range(20):
        await repository.add("notify.telegram", {"n": index})
    await db_session.commit()

    running = 0
    peak = 0

    async def slow(_: dict[str, object]) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0)
        running -= 1

    dispatcher = OutboxDispatcher()
    dispatcher.register("notify.telegram", slow)

    delivered = await dispatcher.process(db_session, limit=20, concurrency=10)

    assert delivered == 20
    assert peak == 10


async def test_drain_empties_a_queue_longer_than_one_batch(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Крон идёт раз в минуту: остаток пачки не должен ждать следующей минуты."""
    from repibot_core.db.engine import create_session_factory

    repository = OutboxRepository(db_session)
    for index in range(150):
        await repository.add("notify.telegram", {"n": index})
    await db_session.commit()

    async def noop(_: dict[str, object]) -> None:
        return None

    dispatcher = OutboxDispatcher()
    dispatcher.register("notify.telegram", noop)

    delivered = await dispatcher.drain(create_session_factory(engine))

    assert delivered == 150


async def test_drain_keeps_going_after_a_partly_failed_batch(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Часть пачки всегда падает: люди блокируют бота, адреса протухают.

    Считать признаком пустой очереди неполную доставку значит останавливать
    разбор на первом же заблокировавшем — и возвращать тот самый потолок в
    одну пачку за минуту, ради снятия которого дренаж и написан.
    """
    from repibot_core.db.engine import create_session_factory

    repository = OutboxRepository(db_session)
    for index in range(150):
        await repository.add("notify.telegram", {"n": index})
    await db_session.commit()

    async def blocked_for_the_first_ten(payload: dict[str, object]) -> None:
        if int(str(payload["n"])) < 10:
            msg = "bot was blocked by the user"
            raise RuntimeError(msg)

    dispatcher = OutboxDispatcher()
    dispatcher.register("notify.telegram", blocked_for_the_first_ten)

    delivered = await dispatcher.drain(create_session_factory(engine))

    # Девяносто из первой пачки и все пятьдесят из второй. Десять неудачных
    # ждут своей задержки и придут следующим прогоном.
    assert delivered == 140


async def test_waking_a_dead_broker_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сообщение уже в базе: худшее, чего заслуживает молчащий брокер, — ожидание крона."""
    from repibot_core import tasks

    async def _refuse() -> None:
        msg = "брокер недоступен"
        raise RuntimeError(msg)

    monkeypatch.setattr(tasks.process_outbox, "kiq", _refuse)

    await tasks.wake_outbox()


async def test_waking_asks_the_worker_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пробуждение обязано доходить до брокера: молчаливое `pass` тоже «не падает»."""
    from repibot_core import tasks

    kicks = 0

    async def _count() -> None:
        nonlocal kicks
        kicks += 1

    monkeypatch.setattr(tasks.process_outbox, "kiq", _count)

    await tasks.wake_outbox()

    assert kicks == 1


def test_retry_delays_grow() -> None:
    assert RETRY_DELAYS[0] < RETRY_DELAYS[-1]
    assert len(RETRY_DELAYS) == MAX_ATTEMPTS
    assert RETRY_DELAYS[0] == timedelta(seconds=10)
