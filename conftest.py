"""Общие фикстуры и тестовое окружение для всех пакетов workspace.

Один файл на весь репозиторий, а не по одному на пакет: конфигурация тестов
одинакова везде, а несколько модулей с именем `conftest` ломают разрешение
имён в mypy.

Окружение выставляется на уровне импорта, а не фикстурой: `repibot_api.main`
собирает приложение прямо при импорте модуля, то есть ещё на этапе сбора
тестов, когда ни одна фикстура не отработала.

Postgres поднимается в контейнере — SQLite здесь не подходит. Мы полагаемся на
поведение конкретной СУБД (типы, ограничения, миграции), и проверять их на
другой базе — значит проверять не то, что поедет в продакшен. Контейнер
создаётся лениво, только если тест запросил фикстуру.
"""

import os
from collections.abc import AsyncIterator, Iterator

_TEST_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/repibot",
    "VALKEY_URL": "redis://localhost:6379/0",
    "BOT_TOKEN": "123456:test-token",
    "BOT_WEBHOOK_SECRET": "webhook-secret",
    "BOT_WEBHOOK_BASE_URL": "https://example.org",
    "REMNAWAVE_BASE_URL": "https://panel.example.org",
    "REMNAWAVE_TOKEN": "panel-token",
    "JWT_SECRET": "jwt-secret",
    "ENCRYPTION_KEY": "encryption-key",
    "PUBLIC_WEB_URL": "https://example.org",
    "PUBLIC_APP_URL": "https://example.org/app",
}

for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)

# Импорты ниже — только после подготовки окружения.
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: E402
from testcontainers.community.postgres import PostgresContainer  # noqa: E402

from repibot_core.db.engine import create_engine  # noqa: E402
from repibot_core.settings import get_settings  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest_asyncio.fixture
async def engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(postgres_url)
    yield engine
    await engine.dispose()
