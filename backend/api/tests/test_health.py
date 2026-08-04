"""Проверка живости отвечает раздельно по каждой зависимости.

Ответ «что-то не работает» бесполезен в три часа ночи — нужно знать, что именно.
"""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from repibot_api.main import create_app


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
