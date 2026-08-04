"""Проверка живости: раздельный статус по каждой зависимости."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from repibot_core.db.engine import check_database, create_engine
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    valkey: bool


async def check_valkey(url: str) -> bool:
    client: Redis = Redis.from_url(url)
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


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    settings = get_settings()

    engine = create_engine(settings.database_url)
    try:
        database_ok = await check_database(engine)
    finally:
        await engine.dispose()

    valkey_ok = await check_valkey(settings.valkey_url)

    healthy = database_ok and valkey_ok
    if not healthy:
        response.status_code = 503
    return HealthResponse(
        status="ok" if healthy else "degraded", database=database_ok, valkey=valkey_ok
    )
