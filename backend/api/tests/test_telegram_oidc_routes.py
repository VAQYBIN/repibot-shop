"""Браузерный вход через Telegram: редиректы, state, cookie."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from pydantic import SecretStr

from repibot_core.integrations.telegram.oidc import ISSUER

pytestmark = pytest.mark.docker

CLIENT_ID = "1234567:web"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KID = "test-key"


def _jwks() -> dict[str, Any]:
    jwk = dict(jwt.algorithms.RSAAlgorithm.to_jwk(_KEY.public_key(), as_dict=True))
    jwk.update({"kid": _KID, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def _id_token(sub: str = "777000") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": sub,
            "name": "Тест",
            "preferred_username": "tester",
            "iat": now,
            "exp": now + 300,
        },
        _KEY,
        algorithm="RS256",
        headers={"kid": _KID},
    )


@pytest.fixture
def telegram_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подставляет client_id и перехватывает сеть к oauth.telegram.org."""
    from repibot_api.routers import auth as auth_router
    from repibot_core.settings import Settings, get_settings

    settings = get_settings().model_copy(
        update={
            "telegram_oidc_client_id": CLIENT_ID,
            "telegram_oidc_client_secret": SecretStr("secret"),
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json=_jwks())
        return httpx.Response(200, json={"id_token": _id_token()})

    def fake_settings() -> Settings:
        return settings

    monkeypatch.setattr(auth_router, "get_settings", fake_settings)
    monkeypatch.setattr(
        auth_router,
        "oidc_http_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_start_redirects_to_telegram_with_state(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    response = await api_client.get("/api/auth/telegram/start")

    assert response.status_code == 307
    target = urlsplit(response.headers["location"])
    assert target.netloc == "oauth.telegram.org"
    query = parse_qs(target.query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"][0]


async def test_start_without_configuration_returns_to_login(api_client: AsyncClient) -> None:
    """Не настроенный OIDC не должен выглядеть пятисоткой."""
    response = await api_client.get("/api/auth/telegram/start")

    assert response.status_code == 307
    assert "/login?error=telegram_unavailable" in response.headers["location"]


async def test_callback_signs_in_and_sets_cookie(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    started = await api_client.get("/api/auth/telegram/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]

    response = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "the-code", "state": state}
    )

    assert response.status_code == 307
    assert response.headers["location"].endswith("/account")
    assert "Path=/api/auth/refresh" in response.headers["set-cookie"]


async def test_callback_keeps_access_token_out_of_the_address_bar(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """Токен в адресной строке остался бы в истории браузера и журнале прокси."""
    started = await api_client.get("/api/auth/telegram/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]

    response = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "the-code", "state": state}
    )

    assert urlsplit(response.headers["location"]).query == ""


async def test_callback_with_unknown_state_is_refused(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """State не наш — либо подделка, либо просроченная попытка."""
    response = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "the-code", "state": "самодельный"}
    )

    assert response.status_code == 307
    assert "/login?error=token_invalid" in response.headers["location"]


async def test_callback_needs_the_browser_that_started_the_login(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """Чужой браузер с готовым кодом не должен усадить человека в чужой аккаунт.

    Злоумышленник начинает вход у себя, доводит его до рабочего `code` и
    подсовывает жертве ссылку возврата. Без привязки к браузеру жертва молча
    оказалась бы в аккаунте злоумышленника и платила бы за его подписку.
    """
    started = await api_client.get("/api/auth/telegram/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    api_client.cookies.delete("repibot_oidc", path="/api/auth/telegram")

    response = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "the-code", "state": state}
    )

    assert "/login?error=token_invalid" in response.headers["location"]


async def test_callback_refuses_a_foreign_binding(
    api_client: AsyncClient, telegram_configured: None
) -> None:
    """Подставленное значение cookie не проходит: оно сверяется с сохранённым."""
    started = await api_client.get("/api/auth/telegram/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    # Значение только из ASCII: cookie переносит байты, а не текст.
    api_client.cookies.set("repibot_oidc", "forged-binding", path="/api/auth/telegram")

    response = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "the-code", "state": state}
    )

    assert "/login?error=token_invalid" in response.headers["location"]


async def test_state_works_only_once(api_client: AsyncClient, telegram_configured: None) -> None:
    started = await api_client.get("/api/auth/telegram/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    await api_client.get("/api/auth/telegram/callback", params={"code": "one", "state": state})

    repeated = await api_client.get(
        "/api/auth/telegram/callback", params={"code": "two", "state": state}
    )

    assert "/login?error=token_invalid" in repeated.headers["location"]


async def test_methods_tell_the_front_end_what_is_available(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/auth/methods")

    assert response.status_code == 200
    assert response.json() == {"telegram": False, "passkey": True}
