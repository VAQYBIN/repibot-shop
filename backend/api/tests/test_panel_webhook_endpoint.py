"""Приёмник событий панели."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Iterator

import pytest
from httpx import AsyncClient

from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

SECRET = "секрет-панели-для-тестов"


def _body(event: str = "user.revoked") -> bytes:
    return json.dumps(
        {
            "scope": "user",
            "event": event,
            "timestamp": "2026-08-06T12:00:00Z",
            "data": {"id": 42},
        },
        ensure_ascii=False,
    ).encode()


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def panel_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("REMNAWAVE_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_signed_event_is_accepted(
    api_client: AsyncClient, panel_webhook_secret: None
) -> None:
    body = _body()
    response = await api_client.post(
        "/webhook/remnawave",
        content=body,
        headers={"content-type": "application/json", "x-remnawave-signature": _sign(body)},
    )
    assert response.status_code == 204


async def test_wrong_signature_is_refused(
    api_client: AsyncClient, panel_webhook_secret: None
) -> None:
    body = _body()
    response = await api_client.post(
        "/webhook/remnawave",
        content=body,
        headers={
            "content-type": "application/json",
            "x-remnawave-signature": _sign("чужое".encode()),
        },
    )
    assert response.status_code == 403


async def test_missing_signature_is_refused(
    api_client: AsyncClient, panel_webhook_secret: None
) -> None:
    response = await api_client.post(
        "/webhook/remnawave", content=_body(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 403


async def test_unconfigured_secret_refuses_everything(api_client: AsyncClient) -> None:
    """Пустой секрет — «вебхуки не настроены», а не «принимай что угодно»."""
    body = _body()
    response = await api_client.post(
        "/webhook/remnawave",
        content=body,
        headers={"content-type": "application/json", "x-remnawave-signature": _sign(body)},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "webhooks_disabled"


async def test_repeated_delivery_is_still_ok(
    api_client: AsyncClient, panel_webhook_secret: None
) -> None:
    """Повтор не обрабатывается второй раз, но и ошибкой не считается.

    Панель на ошибку ответит новой попыткой, и приём зациклится.
    """
    body = _body()
    headers = {"content-type": "application/json", "x-remnawave-signature": _sign(body)}
    first = await api_client.post("/webhook/remnawave", content=body, headers=headers)
    second = await api_client.post("/webhook/remnawave", content=body, headers=headers)
    assert (first.status_code, second.status_code) == (204, 204)
