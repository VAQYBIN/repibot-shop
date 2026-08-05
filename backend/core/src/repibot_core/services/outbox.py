"""Разбор очереди надёжной доставки.

Диспетчер не знает, что делают обработчики: он отвечает за попытки, задержки
и за то, что сообщение не потеряется и не отправится дважды.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.outbox import OutboxRepository

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
        self, session: AsyncSession, *, limit: int = 20, now: datetime | None = None
    ) -> int:
        """Обрабатывает пачку сообщений. Возвращает число доставленных."""
        moment = now or datetime.now(UTC)
        repository = OutboxRepository(session)
        delivered = 0

        for message in await repository.take_batch(limit=limit, now=moment):
            handler = self._handlers.get(message.topic)
            if handler is None:
                # Тема появится после выката новой версии. Сообщение остаётся
                # в очереди: терять его из-за порядка обновления сервисов нельзя.
                await repository.postpone(
                    message, f"нет обработчика для темы {message.topic}", RETRY_DELAYS[0]
                )
                continue

            try:
                await handler(message.payload)
            # Ловим всё: падение одного обработчика не должно останавливать
            # разбор остальных сообщений.
            except Exception as error:
                attempt = message.attempts
                if attempt + 1 >= MAX_ATTEMPTS:
                    # Попытки исчерпаны. Сообщение закрывается с сохранённой
                    # ошибкой: висящая вечно строка мешает разбирать остальные.
                    message.last_error = str(error)[:1000]
                    message.attempts = attempt + 1
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
                continue

            await repository.mark_processed(message)
            delivered += 1

        await session.commit()
        return delivered
