"""Миграции должны применяться на чистой базе и откатываться обратно."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from repibot_core.db.base import Base
from repibot_core.db.engine import check_database, create_engine
from repibot_core.db.models import User  # noqa: F401 — регистрация в метаданных

pytestmark = pytest.mark.docker


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("+asyncpg", "+psycopg"))
    return config


def test_migrations_apply_and_rollback(postgres_url: str) -> None:
    config = _alembic_config(postgres_url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


async def test_users_table_exists_after_migration(postgres_url: str, engine: AsyncEngine) -> None:
    command.upgrade(_alembic_config(postgres_url), "head")

    async with engine.connect() as connection:
        result = await connection.execute(
            text("select column_name from information_schema.columns where table_name = 'users'")
        )
        columns = {row[0] for row in result}

    assert {"id", "created_at", "updated_at"} <= columns


def test_migrations_match_the_models(postgres_url: str) -> None:
    """Модель и миграции расходятся молча.

    Правку модели без новой миграции обнаружит только продакшен: приложение
    обращается к столбцу, которого в базе нет. Autogenerate сравнивает
    фактическую схему с метаданными и показывает разницу до выката.
    """
    command.upgrade(_alembic_config(postgres_url), "head")

    engine = create_sync_engine(postgres_url.replace("+asyncpg", "+psycopg"))
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True, "target_metadata": Base.metadata}
            )
            difference = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert difference == [], f"схема разошлась с моделями: {difference}"


async def test_check_database_returns_true_when_reachable(engine: AsyncEngine) -> None:
    assert await check_database(engine) is True


async def test_check_database_returns_false_when_unreachable() -> None:
    engine = create_engine("postgresql+asyncpg://nobody:nobody@127.0.0.1:1/nothing")
    try:
        assert await check_database(engine) is False
    finally:
        await engine.dispose()
