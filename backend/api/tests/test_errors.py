"""Ошибки отдаются одним форматом — клиенту не нужно разбирать три разных."""

from collections.abc import AsyncIterator

import pytest
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

    @app.get("/typed/{value}")
    async def typed(value: int) -> dict[str, int]:
        return {"value": value}

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


async def test_unknown_route_uses_the_common_shape(client: AsyncClient) -> None:
    """FastAPI по умолчанию отдаёт {"detail": ...} — клиенту пришлось бы
    разбирать два разных формата в зависимости от того, кто ответил."""
    response = await client.get("/такого-маршрута-нет")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_validation_error_uses_the_common_shape(client: AsyncClient) -> None:
    response = await client.get("/typed/не-число")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    # Сведения по полям сохраняются: без них форма не покажет, что именно неверно.
    assert body["error"]["details"]


@pytest.mark.parametrize(
    "path", ["/boom", "/unexpected", "/такого-маршрута-нет", "/typed/не-число"]
)
async def test_every_error_response_carries_request_id(client: AsyncClient, path: str) -> None:
    """Ответ 500 собирается вне пользовательских middleware, и заголовок
    приходится ставить в самом обработчике — иначе именно на нём его и нет."""
    response = await client.get(path)

    assert response.headers.get("x-request-id")
