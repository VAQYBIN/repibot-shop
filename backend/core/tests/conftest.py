"""Общие фикстуры. Postgres поднимается в контейнере — SQLite здесь не подходит.

Мы полагаемся на поведение конкретной СУБД (типы, ограничения, миграции),
и проверять их на другой базе — значит проверять не то, что поедет в продакшен.
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.community.postgres import PostgresContainer

from repibot_core.db.engine import create_engine


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest_asyncio.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(postgres_url)
    yield engine
    await engine.dispose()
