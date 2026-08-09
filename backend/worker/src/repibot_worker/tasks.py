"""Задачи воркера.

Своя здесь одна — заглушка heartbeat: она подтверждает, что очередь,
планировщик и подключение к базе из воркера действительно работают.
Остальные задачи объявлены в core и реэкспортируются: воркер запускается по
пути `repibot_worker.tasks` и должен видеть их все.
"""

from __future__ import annotations

import logging

from repibot_core.db.engine import check_database, create_engine
from repibot_core.settings import get_settings
from repibot_core.tasks import process_outbox, reconcile_pending_payments
from repibot_worker.broker import broker

logger = logging.getLogger(__name__)

__all__ = ["heartbeat", "process_outbox", "reconcile_pending_payments"]


@broker.task(schedule=[{"cron": "*/5 * * * *"}])
async def heartbeat() -> dict[str, str]:
    """Проверяет, что воркер жив и видит базу."""
    engine = create_engine(get_settings().database_url)
    try:
        database_ok = await check_database(engine)
    finally:
        await engine.dispose()

    logger.info("heartbeat: база %s", "доступна" if database_ok else "недоступна")
    return {"status": "alive", "database": "ok" if database_ok else "down"}
