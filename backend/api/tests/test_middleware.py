"""Идентификатор запроса: сквозной внутри обработки и не переживающий её."""

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from repibot_api.main import create_app
from repibot_core.logging import request_id_var


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"ok": "1"}

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_incoming_request_id_is_reused(client: AsyncClient) -> None:
    """Идентификатор приходит от внешнего прокси — цепочку рвать нельзя."""
    response = await client.get("/ok", headers={"X-Request-ID": "from-proxy"})

    assert response.headers["x-request-id"] == "from-proxy"


async def test_request_id_is_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/ok")

    assert response.headers["x-request-id"]


async def test_request_id_does_not_outlive_the_request(client: AsyncClient) -> None:
    """Значение переживало запрос и доставалось всему, что логируется после него.

    Между запросами оно не течёт — каждый обрабатывается в своей задаче, — но
    фоновая работа в том же контексте получала бы чужой идентификатор.
    """
    assert request_id_var.get() is None

    # Значение латиницей: заголовок HTTP кодируется в ascii.
    await client.get("/ok", headers={"X-Request-ID": "inside-request"})

    assert request_id_var.get() is None
