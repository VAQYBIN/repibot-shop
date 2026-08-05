"""Клиент панели: авторизация, ретраи, поведение при отказе.

Панель может стоять на другом сервере и уходить в перезагрузку ровно в момент
оплаты — поведение при отказах здесь важнее набора методов.
"""

import httpx
import pytest

from repibot_core.integrations.remnawave.client import (
    RemnawaveClient,
    RemnawaveUnavailable,
    create_remnawave_client,
)
from repibot_core.settings import get_settings


def _client(transport: httpx.MockTransport) -> RemnawaveClient:
    client = RemnawaveClient(
        base_url="https://panel.example.org", token="panel-token", timeout=1.0, max_attempts=3
    )
    client._http = httpx.AsyncClient(
        transport=transport,
        base_url="https://panel.example.org",
        headers={"Authorization": "Bearer panel-token"},
    )
    return client


async def test_request_sends_bearer_token() -> None:
    seen: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"response": {}})

    client = _client(httpx.MockTransport(handle))
    await client.request("GET", "/api/system/health")
    await client.aclose()

    assert seen["authorization"] == "Bearer panel-token"


async def test_retries_on_server_error_then_succeeds() -> None:
    calls = {"count": 0}

    def handle(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"response": {"ok": True}})

    client = _client(httpx.MockTransport(handle))
    response = await client.request("GET", "/api/system/health")
    await client.aclose()

    assert calls["count"] == 3
    assert response.json()["response"]["ok"] is True


async def test_raises_unavailable_after_exhausting_retries() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    client = _client(httpx.MockTransport(handle))
    with pytest.raises(RemnawaveUnavailable):
        await client.request("GET", "/api/system/health")
    await client.aclose()


async def test_client_errors_are_not_retried() -> None:
    """Повторять запрос, на который панель ответила «нет такого пользователя», бессмысленно."""
    calls = {"count": 0}

    def handle(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404, json={"message": "not found"})

    client = _client(httpx.MockTransport(handle))
    response = await client.request("GET", "/api/users/by-uuid/unknown")
    await client.aclose()

    assert calls["count"] == 1
    assert response.status_code == 404


async def test_number_of_attempts_matches_the_setting() -> None:
    """Параметр называется «попытки», а не «повторы»: три означает три запроса,
    а не один плюс три. Разница в треть нагрузки на падающую панель."""
    calls = {"count": 0}

    def handle(_request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503)

    client = RemnawaveClient(
        base_url="https://panel.example.org", token="panel-token", timeout=1.0, max_attempts=2
    )
    client._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="https://panel.example.org"
    )

    with pytest.raises(RemnawaveUnavailable):
        await client.request("GET", "/api/system/health")
    await client.aclose()

    assert calls["count"] == 2


async def test_factory_takes_everything_from_settings() -> None:
    """Настройки таймаута и числа попыток иначе остаются мёртвыми: клиент
    создаётся вручную, и значения из конфигурации до него не доходят."""
    settings = get_settings()
    client = create_remnawave_client()

    try:
        assert client.max_attempts == settings.remnawave_max_attempts
        assert client._http.timeout.connect == settings.remnawave_timeout_seconds
        assert str(client._http.base_url) == settings.remnawave_base_url.rstrip("/")
        assert (
            client._http.headers["authorization"]
            == f"Bearer {settings.remnawave_token.get_secret_value()}"
        )
    finally:
        await client.aclose()


async def test_connection_error_is_wrapped() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("нет маршрута до панели")

    client = _client(httpx.MockTransport(handle))
    with pytest.raises(RemnawaveUnavailable):
        await client.request("GET", "/api/system/health")
    await client.aclose()
