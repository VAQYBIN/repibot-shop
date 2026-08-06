"""Вход через Telegram: PKCE, обмен кода и проверка ID-токена."""

from __future__ import annotations

import base64
import hashlib
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fakeredis.aioredis import FakeRedis
from jwt.algorithms import RSAAlgorithm
from pydantic import SecretStr

from repibot_core.integrations.telegram.oidc import ISSUER, TelegramOidc, is_configured
from repibot_core.security.pkce import code_challenge, generate_code_verifier
from repibot_core.services.auth.types import AuthError
from repibot_core.settings import Settings, get_settings

CLIENT_ID = "1234567:web"
REDIRECT = "https://example.org/api/auth/telegram/callback"

Handler = Callable[[httpx.Request], httpx.Response]

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_KID = "test-key"


def _jwks() -> dict[str, Any]:
    exported = RSAAlgorithm.to_jwk(_KEY.public_key(), as_dict=True)
    return {"keys": [{**exported, "kid": _KID, "alg": "RS256", "use": "sig"}]}


def _id_token(**overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        # Как в настоящем токене: sub — непрозрачное значение, а Telegram ID
        # лежит в отдельном claim id. Значения намеренно разные, иначе тест
        # прошёл бы и при чтении не того поля.
        "sub": "1273349464943926156",
        "id": 777000,
        "name": "Тест",
        "preferred_username": "tester",
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": _KID})


def _settings() -> Settings:
    return get_settings().model_copy(
        update={
            "telegram_oidc_client_id": CLIENT_ID,
            # Именно SecretStr, а не строка: model_copy значения не проверяет,
            # и подстановка str обернулась бы падением на get_secret_value.
            "telegram_oidc_client_secret": SecretStr("secret"),
        }
    )


def _service(handler: Handler) -> TelegramOidc:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TelegramOidc(_settings(), FakeRedis(), client=client)


def _serve(token: str | None = None) -> Handler:
    """Отвечает за оба обращения к Telegram: JWKS и обмен кода."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json=_jwks())
        return httpx.Response(200, json={"id_token": token or _id_token()})

    return handler


def test_code_challenge_is_sha256_in_base64url() -> None:
    verifier = generate_code_verifier()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode()

    assert code_challenge(verifier) == expected.rstrip("=")
    # RFC 7636 требует от 43 до 128 символов.
    assert 43 <= len(verifier) <= 128


async def test_authorization_url_carries_pkce_and_scopes() -> None:
    service = _service(_serve())

    url = service.authorization_url(
        state="state-1", code_challenge="challenge-1", redirect_uri=REDIRECT
    )

    query = parse_qs(urlsplit(url).query)
    assert query["client_id"] == [CLIENT_ID]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == ["challenge-1"]
    assert query["state"] == ["state-1"]
    assert "telegram:bot_access" in query["scope"][0]


async def test_valid_id_token_yields_identity() -> None:
    service = _service(_serve())

    identity = await service.verify_id_token(_id_token())

    assert identity.telegram_id == 777000
    assert identity.username == "tester"
    assert identity.name == "Тест"


async def test_forged_signature_is_rejected() -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = jwt.encode(
        {"iss": ISSUER, "aud": CLIENT_ID, "sub": "1", "exp": int(time.time()) + 300},
        other,
        algorithm="RS256",
        headers={"kid": _KID},
    )
    service = _service(_serve())

    with pytest.raises(AuthError) as failure:
        await service.verify_id_token(forged)
    assert failure.value.code == "invalid_credentials"


async def test_token_for_another_client_is_rejected() -> None:
    service = _service(_serve())

    with pytest.raises(AuthError):
        await service.verify_id_token(_id_token(aud="somebody-else"))


async def test_expired_token_is_rejected() -> None:
    service = _service(_serve())
    stale = int(time.time()) - 3600

    with pytest.raises(AuthError):
        await service.verify_id_token(_id_token(iat=stale, exp=stale + 300))


async def test_token_from_another_issuer_is_rejected() -> None:
    service = _service(_serve())

    with pytest.raises(AuthError):
        await service.verify_id_token(_id_token(iss="https://evil.example.org"))


async def test_exchange_sends_verifier_and_returns_id_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("jwks.json"):
            return httpx.Response(200, json=_jwks())
        seen.update({key: value[0] for key, value in parse_qs(request.content.decode()).items()})
        return httpx.Response(200, json={"id_token": _id_token()})

    service = _service(handler)

    token = await service.exchange(code="the-code", code_verifier="verifier", redirect_uri=REDIRECT)

    assert token
    assert seen["grant_type"] == "authorization_code"
    assert seen["code"] == "the-code"
    assert seen["code_verifier"] == "verifier"
    assert seen["redirect_uri"] == REDIRECT


async def test_refused_exchange_becomes_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    service = _service(handler)

    with pytest.raises(AuthError) as failure:
        await service.exchange(code="stale", code_verifier="v", redirect_uri=REDIRECT)
    assert failure.value.code == "invalid_credentials"


async def test_jwks_is_fetched_once_and_cached() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("jwks.json"):
            calls["count"] += 1
            return httpx.Response(200, json=_jwks())
        return httpx.Response(404)

    service = _service(handler)

    await service.verify_id_token(_id_token())
    await service.verify_id_token(_id_token())

    assert calls["count"] == 1


async def test_secrets_never_reach_the_log(caplog: pytest.LogCaptureFixture) -> None:
    """Ни секрет клиента, ни код, ни verifier, ни токен в журнал не попадают."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant", "code": "the-code"})

    service = _service(handler)

    with caplog.at_level("DEBUG"), pytest.raises(AuthError):
        await service.exchange(code="the-code", code_verifier="the-verifier", redirect_uri=REDIRECT)

    written = "\n".join(
        [record.getMessage() for record in caplog.records]
        + [str(record.__dict__) for record in caplog.records]
    )
    assert "the-code" not in written
    assert "the-verifier" not in written
    assert "secret" not in written


def test_client_id_without_secret_is_not_configured() -> None:
    """Половина пары из BotFather хуже, чем ничего.

    С одним Client ID кнопка выглядит рабочей, а вход обрывается на обмене кода —
    уже после того, как человек подтвердил доступ в Telegram.
    """
    settings = get_settings().model_copy(
        update={"telegram_oidc_client_id": CLIENT_ID, "telegram_oidc_client_secret": SecretStr("")}
    )

    assert is_configured(settings) is False


def test_both_halves_make_it_configured() -> None:
    assert is_configured(_settings()) is True


async def test_identity_comes_from_id_claim_not_sub() -> None:
    """sub — непрозрачное значение, Telegram ID лежит отдельно.

    Проверено живым входом 2026-08-06: по sub человек получал второй аккаунт
    вместо своего и не проходил по списку ADMIN_TELEGRAM_IDS. В
    discovery-документе claim `id` не объявлен, список claims там неполный.
    """
    service = _service(_serve())

    identity = await service.verify_id_token(_id_token(sub="1273349464943926156", id=728763367))

    assert identity.telegram_id == 728763367


async def test_token_without_id_claim_is_refused() -> None:
    """Аккаунт по одному sub заводить нельзя: он не совпадёт ни с ботом, ни с MiniApp."""
    now = int(time.time())
    without_id = jwt.encode(
        {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "1273349464943926156",
            "iat": now,
            "exp": now + 300,
        },
        _KEY,
        algorithm="RS256",
        headers={"kid": _KID},
    )
    service = _service(_serve(without_id))

    with pytest.raises(AuthError) as failure:
        await service.verify_id_token(without_id)
    assert failure.value.code == "invalid_credentials"
