"""Движок и фабрика сессий."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


def create_engine(url: str, *, echo: bool = False, connect_timeout: float = 5.0) -> AsyncEngine:
    """Создаёт асинхронный движок.

    pool_pre_ping спасает от накопленных мёртвых соединений после перезапуска
    базы — без него первый запрос после рестарта Postgres падает.

    connect_timeout ограничивает только установку соединения. Ограничивать здесь
    же время выполнения запроса (command_timeout) нельзя: под него попали бы и
    долгие выборки отчётов, которые появятся в админке.
    """
    return create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"timeout": connect_timeout},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def check_database(engine: AsyncEngine) -> bool:
    """Проверяет доступность базы. Используется в /health."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except (SQLAlchemyError, OSError):
        logger.warning("база данных недоступна", exc_info=True)
        return False
    return True
