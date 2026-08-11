"""Разбор очереди надёжной доставки.

Диспетчер не знает, что делают обработчики: он отвечает за попытки, задержки
и за то, что сообщение не потеряется и не отправится дважды.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.db.models import NotificationDelivery, OutboxMessage
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]

# Задержки перед попытками. Последняя попытка — примерно через полчаса после
# первой: этого хватает, чтобы переждать перезапуск почтового сервера, и не
# хватает, чтобы очередь превратилась в свалку.
RETRY_DELAYS: tuple[timedelta, ...] = (
    timedelta(seconds=10),
    timedelta(seconds=60),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=30),
)
MAX_ATTEMPTS = len(RETRY_DELAYS)


class OutboxDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, topic: str, handler: Handler) -> None:
        self._handlers[topic] = handler

    async def process(
        self,
        session: AsyncSession,
        *,
        limit: int | None = None,
        concurrency: int | None = None,
        now: datetime | None = None,
    ) -> int:
        """Обрабатывает пачку сообщений. Возвращает число доставленных.

        Отправки идут одновременно, а записи в базу — по очереди: одна сессия
        SQLAlchemy не переживает параллельных запросов, и попытка сэкономить
        здесь даёт `InterfaceError` вместо ускорения.
        """
        settings = get_settings()
        size = limit if limit is not None else settings.outbox_batch_size
        parallel = concurrency if concurrency is not None else settings.outbox_concurrency
        moment = now or datetime.now(UTC)
        repository = OutboxRepository(session)

        pending: list[OutboxMessage] = []
        for message in await repository.take_batch(limit=size, now=moment):
            handler = self._handlers.get(message.topic)
            if handler is None:
                # Тема появится после выката новой версии. Сообщение остаётся
                # в очереди: терять его из-за порядка обновления сервисов нельзя.
                await repository.postpone(
                    message, f"нет обработчика для темы {message.topic}", RETRY_DELAYS[0]
                )
                continue
            pending.append(message)

        semaphore = asyncio.Semaphore(parallel)

        async def run(message: OutboxMessage) -> Exception | None:
            async with semaphore:
                try:
                    await self._handlers[message.topic](message.payload)
                # Ловим всё: падение одного обработчика не должно останавливать
                # разбор остальных сообщений.
                except Exception as error:
                    return error
                return None

        outcomes = await asyncio.gather(*(run(message) for message in pending))

        delivered = 0
        for message, error in zip(pending, outcomes, strict=True):
            if error is None:
                await _mark_delivery(session, message.payload, status="sent", error=None)
                await repository.mark_processed(message)
                delivered += 1
                continue
            attempt = message.attempts
            if attempt + 1 >= MAX_ATTEMPTS:
                # Попытки исчерпаны. Сообщение закрывается с сохранённой
                # ошибкой: висящая вечно строка мешает разбирать остальные.
                message.last_error = str(error)[:1000]
                message.attempts = attempt + 1
                await _mark_delivery(
                    session, message.payload, status="failed", error=message.last_error
                )
                await repository.mark_processed(message)
                logger.error(
                    "сообщение outbox отброшено после %s попыток",
                    MAX_ATTEMPTS,
                    extra={"topic": message.topic, "outbox_id": message.id},
                )
            else:
                await repository.postpone(message, str(error), RETRY_DELAYS[attempt])
                logger.warning(
                    "сообщение outbox отложено",
                    extra={"topic": message.topic, "outbox_id": message.id},
                )

        await session.commit()
        return delivered

    async def drain(
        self, factory: async_sessionmaker[AsyncSession], *, max_seconds: float = 50.0
    ) -> int:
        """Разбирает очередь до пустоты или до истечения времени прогона.

        Потолок по времени, а не по числу пачек: задача идёт раз в минуту, и
        прогон, переживший следующий запуск, разбирал бы очередь вдвоём сам с
        собой. Своя сессия на пачку: `process` закрывает транзакцию commit'ом.

        Признак конца — пачка, не доставившая ничего, а не пачка неполная.
        Часть сообщений падает всегда: люди блокируют бота, адреса протухают.
        Считать неполную доставку пустой очередью значит останавливать разбор
        на первом же заблокировавшем и возвращать тот потолок в одну пачку за
        минуту, ради снятия которого дренаж и написан.
        """
        deadline = time.monotonic() + max_seconds
        delivered = 0
        while time.monotonic() < deadline:
            async with factory() as session:
                batch = await self.process(session)
            delivered += batch
            if batch == 0:
                break
        return delivered


async def _mark_delivery(
    session: AsyncSession, payload: dict[str, Any], *, status: str, error: str | None
) -> None:
    """Переносит итог разбора очереди в строку доставки, которую можно опросить."""
    delivery_id = payload.get("delivery_id")
    if type(delivery_id) is not int:
        return
    delivery = await session.get(NotificationDelivery, delivery_id)
    if delivery is None:
        return
    delivery.status = status
    delivery.error = error
    if status == "sent":
        delivery.sent_at = datetime.now(UTC)
