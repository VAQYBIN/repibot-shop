"""Проверка живости отвечает раздельно по каждой зависимости.

Ответ «что-то не работает» бесполезен в три часа ночи — нужно знать, что именно.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from repibot_api.health import check_valkey, get_engine
from repibot_api.main import create_app
from repibot_core.settings import get_settings


def _always(value: bool) -> Callable[..., Coroutine[Any, Any, bool]]:
    async def _inner(*_args: object, **_kwargs: object) -> bool:
        return value

    return _inner


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_health_reports_ok_when_all_dependencies_are_up(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repibot_api.health.check_database", _always(True))
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(True))

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True, "valkey": True}


async def test_health_reports_degraded_when_database_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repibot_api.health.check_database", _always(False))
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(True))

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": False, "valkey": True}


async def test_health_reports_degraded_when_valkey_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repibot_api.health.check_database", _always(True))
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(False))

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["valkey"] is False


async def test_check_valkey_returns_false_when_unreachable() -> None:
    """Без мока: redis поднимает собственный ConnectionError, не наследник встроенного.

    Остальные тесты подменяют check_valkey целиком и ветку отказа не исполняют —
    ошибка в списке перехватываемых исключений видна только здесь.
    """
    assert await check_valkey("redis://127.0.0.1:1/0") is False


async def test_health_reports_degraded_when_valkey_is_really_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сквозная проверка: недоступная зависимость даёт 503, а не 500."""
    settings = get_settings().model_copy(update={"valkey_url": "redis://127.0.0.1:1/0"})
    monkeypatch.setattr("repibot_api.health.check_database", _always(True))
    monkeypatch.setattr("repibot_api.health.get_settings", lambda: settings)

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": True, "valkey": False}


def test_engine_is_created_once_and_reused() -> None:
    """Новый движок на каждый запрос — это новый пул соединений на каждый опрос
    наблюдателя, то есть верный способ исчерпать лимит подключений базы."""
    assert get_engine() is get_engine()


async def test_health_gives_up_on_a_hanging_dependency(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Без ограничения по времени проверка живости зависает вместе с зависимостью.

    При потере пакетов подключение не падает, а ждёт минутами, и наблюдатель
    вместо «база недоступна» получает таймаут своего запроса.
    """

    async def _hang(*_args: object, **_kwargs: object) -> bool:
        await asyncio.sleep(60)
        return True

    monkeypatch.setattr("repibot_api.health.check_database", _hang)
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(True))
    monkeypatch.setattr("repibot_api.health.PROBE_TIMEOUT_SECONDS", 0.1)

    started = time.perf_counter()
    response = await client.get("/health")
    elapsed = time.perf_counter() - started

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": False, "valkey": True}
    assert elapsed < 5


async def test_openapi_documents_the_degraded_response(client: AsyncClient) -> None:
    """Клиент генерирует типы из схемы: неописанный 503 для него не существует."""
    schema = (await client.get("/openapi.json")).json()

    assert "503" in schema["paths"]["/health"]["get"]["responses"]


async def test_openapi_schema_is_served(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Re:Pibot Shop API"


async def test_response_carries_request_id_header(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repibot_api.health.check_database", _always(True))
    monkeypatch.setattr("repibot_api.health.check_valkey", _always(True))

    response = await client.get("/health")

    assert response.headers["x-request-id"]
