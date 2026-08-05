"""Задачи воркера.

В этом подпроекте одна задача-заглушка: она подтверждает, что очередь,
планировщик и подключение к базе из воркера действительно работают.
"""

from __future__ import annotations

import logging

from repibot_core.db.engine import check_database, create_engine
from repibot_core.settings import get_settings
from repibot_worker.broker import broker

logger = logging.getLogger(__name__)


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
