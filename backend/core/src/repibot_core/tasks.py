"""Фоновые задачи, которые ставит не только воркер.

Расписание раз в минуту — страховка на случай, если процесс, поставивший
задачу, умер между коммитом и постановкой. Обычный путь короче: сервис ставит
задачу сразу после коммита, и письмо уходит за секунды.
"""

from __future__ import annotations

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.queue import broker
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.settings import get_settings


@broker.task(schedule=[{"cron": "* * * * *"}])
async def process_outbox() -> dict[str, int]:
    engine = create_engine(get_settings().database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            delivered = await _dispatcher().process(session)
    finally:
        await engine.dispose()

    return {"delivered": delivered}


def _dispatcher() -> OutboxDispatcher:
    """Собирается на каждый прогон.

    Обработчики писем появятся в задаче 7 — тогда сборка переедет в
    services.email_dispatch.build_dispatcher, а импорт уйдёт внутрь функции,
    чтобы разорвать цикл: services импортирует эту же задачу, чтобы её поставить.
    """
    return OutboxDispatcher()
