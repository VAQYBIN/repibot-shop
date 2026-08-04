"""Ошибки отдаются одним форматом — клиенту не нужно разбирать три разных."""

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from repibot_api.errors import ApiError
from repibot_api.main import create_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise ApiError(message="тариф не найден", status_code=404, code="plan_not_found")

    @app.get("/unexpected")
    async def unexpected() -> None:
        raise RuntimeError("внутренняя подробность, которой не место в ответе")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_api_error_is_rendered_in_common_shape(client: AsyncClient) -> None:
    response = await client.get("/boom")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "plan_not_found", "message": "тариф не найден"}}


async def test_unexpected_error_does_not_leak_internals(client: AsyncClient) -> None:
    response = await client.get("/unexpected")

    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Внутренняя ошибка"}}
    assert "внутренняя подробность" not in response.text
