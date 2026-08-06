"""Проверка живости: раздельный статус по каждой зависимости."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

# Движок берётся из deps: два пула соединений в одном процессе не нужны.
from repibot_api.deps import get_engine
from repibot_core.db.engine import check_database
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Верхняя граница ожидания каждой зависимости. При потере пакетов подключение
# не отвергается, а висит минутами: наблюдатель вместо «база недоступна»
# получает таймаут собственного запроса и не знает, что именно сломалось.
PROBE_TIMEOUT_SECONDS = 3.0


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    valkey: bool


async def check_valkey(url: str) -> bool:
    # Клиент создаётся на каждый вызов сознательно: проверка живости должна
    # устанавливать соединение заново, иначе она подтверждает работоспособность
    # пула, а не самого Valkey. Соединение здесь одно и оно закрывается.
    client: Redis = Redis.from_url(
        url,
        socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
        socket_timeout=PROBE_TIMEOUT_SECONDS,
    )
    try:
        await client.ping()
    # RedisError, а не встроенный ConnectionError: redis.exceptions.ConnectionError
    # наследуется от RedisError → Exception и мимо OSError проходит насквозь.
    # Непойманное исключение здесь превращает штатный 503 в 500 без указания
    # отказавшей зависимости — ровно то, ради чего эндпоинт и написан.
    except (OSError, RedisError):
        logger.warning("valkey недоступен", exc_info=True)
        return False
    finally:
        await client.aclose()
    return True


async def _probe(check: Coroutine[object, object, bool], name: str) -> bool:
    """Ждёт проверку не дольше PROBE_TIMEOUT_SECONDS; зависшая считается упавшей."""
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            return await check
    except TimeoutError:
        logger.warning("%s не ответил за %s с", name, PROBE_TIMEOUT_SECONDS)
        return False


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Отказала хотя бы одна зависимость"}},
)
async def health(response: Response) -> HealthResponse:
    settings = get_settings()

    database_ok = await _probe(check_database(get_engine()), "база данных")
    valkey_ok = await _probe(check_valkey(settings.valkey_url), "valkey")

    healthy = database_ok and valkey_ok
    if not healthy:
        response.status_code = 503
    return HealthResponse(
        status="ok" if healthy else "degraded", database=database_ok, valkey=valkey_ok
    )
