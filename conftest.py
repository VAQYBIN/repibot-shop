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
    # Не короче 32 символов: настройки отвергают слабый ключ подписи, и PyJWT
    # предупреждает о нём отдельно.
    "JWT_SECRET": "0123456789abcdef0123456789abcdef",
    "ENCRYPTION_KEY": "encryption-key",
    "PUBLIC_WEB_URL": "https://example.org",
    "PUBLIC_APP_URL": "https://example.org/app",
    "ADMIN_TELEGRAM_IDS": "",
    "EMAIL_SENDER": "log",
}

for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)

# Импорты ниже — только после подготовки окружения.
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession  # noqa: E402
from testcontainers.community.postgres import PostgresContainer  # noqa: E402

from repibot_core.db.engine import create_engine, create_session_factory  # noqa: E402
from repibot_core.db.models import User, UserRole  # noqa: E402
from repibot_core.settings import Settings, get_settings  # noqa: E402
from repibot_core.testing.initdata import build_init_data  # noqa: E402
from repibot_core.testing.remnawave import FakePanel  # noqa: E402

# Тесты не читают .env разработчика. Иначе набор проходит или падает в
# зависимости от того, что человек прописал у себя: заполненный
# ADMIN_TELEGRAM_IDS ломает проверку «админов нет по умолчанию», а
# настроенный вход через Telegram — проверку «способ не настроен».
# Значения берутся только из окружения выше.
Settings.model_config["env_file"] = None

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


@pytest_asyncio.fixture
async def db_session(postgres_url: str, engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Чистая база с применёнными миграциями и открытой сессией.

    Схема пересоздаётся на каждый тест: остатки чужих строк дают тесты,
    проходящие по одному и падающие в наборе.
    """
    from alembic import command
    from alembic.config import Config

    from repibot_core.db.engine import create_session_factory

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url.replace("+asyncpg", "+psycopg"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    factory = create_session_factory(engine)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def api_client(
    postgres_url: str, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    """Клиент API с реальной базой и подставным Valkey.

    Postgres нужен настоящий — проверяются ограничения схемы. Valkey заменяется
    fakeredis: кэш и лимиты не зависят от особенностей сервера, а контейнер
    ради них удваивал бы время прогона.
    """
    from alembic import command
    from alembic.config import Config
    from fakeredis.aioredis import FakeRedis

    from repibot_api import deps
    from repibot_api.main import app
    from repibot_core.db.engine import create_session_factory

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url.replace("+asyncpg", "+psycopg"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    factory = create_session_factory(engine)
    redis = FakeRedis()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[deps.db_session] = _session
    app.dependency_overrides[deps.get_redis] = lambda: redis
    # Фабрика из deps собирает движок по DATABASE_URL, а адрес контейнера там
    # неизвестен. Тест читает через неё outbox, поэтому подменяется и она —
    # иначе запрос уйдёт в базу, которой на машине нет.
    monkeypatch.setattr(deps, "get_session_factory", lambda: factory)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as client:
        yield client

    app.dependency_overrides.clear()


# --- роли и панель для админских наборов ---

ADMIN_TELEGRAM_ID = 900_001
SUPPORT_TELEGRAM_ID = 900_002
# Тот же сквад, что перечисляют тарифы в тестах: панель-заглушка обязана его
# знать, иначе сервис тарифов справедливо отвергнет запрос.
PANEL_SQUAD_UUID = "11111111-1111-4111-8111-111111111111"
PANEL_SQUAD_NAME = "Европа"


async def _telegram_token_headers(client: AsyncClient, telegram_id: int) -> dict[str, str]:
    """Access-токен обычным входом через MiniApp.

    Токен не собирается вручную: подписью, сроком и записью сессии занимается
    тот же код, что и в бою, и тест ловит его поломку заодно.
    """
    response = await client.post(
        "/api/auth/telegram/miniapp",
        json={
            "init_data": build_init_data(bot_token=os.environ["BOT_TOKEN"], telegram_id=telegram_id)
        },
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[dict[str, str]]:
    """Заголовок авторизации администратора.

    Роль выдаётся тем же путём, что и в бою, — списком ADMIN_TELEGRAM_IDS при
    входе. Отдельная тестовая ручка «сделать админом» проверяла бы саму себя,
    а не гейт роли.
    """
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", str(ADMIN_TELEGRAM_ID))
    get_settings.cache_clear()

    yield await _telegram_token_headers(api_client, ADMIN_TELEGRAM_ID)

    # Настройки закэшированы с подменённым списком: без сброса следующий тест
    # унаследовал бы чужого администратора.
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def support_headers(api_client: AsyncClient, engine: AsyncEngine) -> dict[str, str]:
    """Заголовок авторизации сотрудника поддержки.

    Списка в окружении для этой роли нет: она проставляется в базе — так же,
    как это будет делать админка. Инвалидация кэша principal не нужна, потому
    что при входе он не наполняется: его читает только проверка токена.
    """
    headers = await _telegram_token_headers(api_client, SUPPORT_TELEGRAM_ID)

    async with create_session_factory(engine)() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == SUPPORT_TELEGRAM_ID)
            .values(role=UserRole.support)
        )
        await session.commit()
    return headers


@pytest.fixture
def fake_panel(monkeypatch: pytest.MonkeyPatch) -> FakePanel:
    """Панель Remnawave в памяти вместо живой.

    Подменяется фабрика клиента в роутере, а не фасад: маршруты, тела запросов
    и разбор ответов при этом проверяются настоящие. Сквадов у панели нет —
    их добавляет тот тест, которому они нужны.
    """
    from repibot_api.routers import admin

    panel = FakePanel()
    monkeypatch.setattr(admin, "panel_client", panel.client)
    return panel


@pytest.fixture
def fake_panel_squad(fake_panel: FakePanel) -> None:
    """Панель с одним сквадом — тем самым, из которого собран тариф теста."""
    fake_panel.add_squad(PANEL_SQUAD_UUID, PANEL_SQUAD_NAME)
