"""Публичные эндпоинты passkey: параметры входа, проверка ответа, лимиты.

Ключ здесь заводится вызовом сервиса, а не через `/api/me/passkeys`: проверяются
эндпоинты входа, и падать от изменений в кабинете этот файл не должен.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from webauthn.helpers import base64url_to_bytes

from repibot_core.ratelimit import OIDC_START_PER_IP, PASSKEY_PER_IP
from repibot_core.security.webauthn import relying_party
from repibot_core.services.auth.passkey import PasskeyAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.challenges import ChallengeStore
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings
from repibot_core.testing.webauthn import SoftAuthenticator

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


def _device() -> SoftAuthenticator:
    party = relying_party(get_settings().public_web_url)
    return SoftAuthenticator(rp_id=party.rp_id, origin=party.origin)


async def _sign_in(client: AsyncClient, email: str = "user@example.org") -> int:
    """Регистрация и подтверждение по ссылке из outbox. Возвращает номер пользователя."""
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": PASSWORD, "language": "ru"}
    )
    assert response.status_code == 202

    from repibot_api.deps import get_session_factory

    async with get_session_factory()() as session:
        row = await session.execute(
            text("select payload from outbox where topic = 'email.verify' order by id desc limit 1")
        )
        link = str(row.scalar_one()["link"])
        user_id = await session.scalar(
            text("select id from users where email = :email"), {"email": email}
        )

    confirmed = await client.post("/api/auth/verify-email", json={"token": link.split("token=")[1]})
    assert confirmed.status_code == 200
    return int(user_id)


async def _register_key(user_id: int, device: SoftAuthenticator, name: str = "Ноутбук") -> None:
    """Заводит ключ через сервис: свой Valkey, потому что challenge живёт до вызова register."""
    from fakeredis.aioredis import FakeRedis

    from repibot_api.deps import get_session_factory

    settings = get_settings()
    redis = FakeRedis()
    async with get_session_factory()() as session:
        auth = AuthService(session, settings, PrincipalCache(redis))
        service = PasskeyAuth(session, settings, auth, ChallengeStore(redis))
        options = await service.registration_options(user_id)
        credential = device.register(base64url_to_bytes(options["challenge"]))
        await service.register(user_id, credential, name)
    await redis.aclose()


async def test_login_options_carry_challenge_and_rp_id(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/auth/passkey/login/options")

    assert response.status_code == 200
    options: dict[str, Any] = response.json()["options"]
    assert options["rpId"] == relying_party(get_settings().public_web_url).rp_id
    assert options["challenge"]


async def test_passkey_signs_in_without_password(api_client: AsyncClient) -> None:
    user_id = await _sign_in(api_client)
    device = _device()
    await _register_key(user_id, device)

    options = await api_client.post("/api/auth/passkey/login/options")
    challenge = base64url_to_bytes(options.json()["options"]["challenge"])
    response = await api_client.post(
        "/api/auth/passkey/login/verify",
        json={"credential": device.authenticate(challenge, user_handle=str(user_id).encode())},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    # Passkey-вход даёт полноценную сессию браузера, значит и refresh-cookie.
    assert "Path=/api/auth/refresh" in response.headers["set-cookie"]


async def test_the_same_answer_does_not_work_twice(api_client: AsyncClient) -> None:
    """Записанный ответ аутентификатора бесполезен: challenge гаснет при первом предъявлении."""
    user_id = await _sign_in(api_client)
    device = _device()
    await _register_key(user_id, device)
    options = await api_client.post("/api/auth/passkey/login/options")
    challenge = base64url_to_bytes(options.json()["options"]["challenge"])
    credential = device.authenticate(challenge, user_handle=str(user_id).encode())

    first = await api_client.post("/api/auth/passkey/login/verify", json={"credential": credential})
    second = await api_client.post(
        "/api/auth/passkey/login/verify", json={"credential": credential}
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "token_invalid"


async def test_unknown_key_is_rejected(api_client: AsyncClient) -> None:
    options = await api_client.post("/api/auth/passkey/login/options")
    challenge = base64url_to_bytes(options.json()["options"]["challenge"])

    response = await api_client.post(
        "/api/auth/passkey/login/verify",
        json={"credential": _device().authenticate(challenge, user_handle=b"1")},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_garbage_credential_is_a_client_error(api_client: AsyncClient) -> None:
    """Мусор в теле — ответ 400 с кодом, а не пятисотка."""
    response = await api_client.post(
        "/api/auth/passkey/login/verify", json={"credential": {"nonsense": True}}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "token_invalid"


async def test_login_options_are_rate_limited(api_client: AsyncClient) -> None:
    for _ in range(PASSKEY_PER_IP.limit):
        allowed = await api_client.post("/api/auth/passkey/login/options")
        assert allowed.status_code == 200

    response = await api_client.post("/api/auth/passkey/login/options")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) > 0


async def test_telegram_start_is_rate_limited(api_client: AsyncClient) -> None:
    """Каждый старт кладёт запись в Valkey на десять минут, поэтому анониму нужен предел.

    Отказ приходит обычной ошибкой API: редирект на страницу входа сообщил бы
    браузеру об успехе попытки, а её не было.
    """
    for _ in range(OIDC_START_PER_IP.limit):
        allowed = await api_client.get("/api/auth/telegram/start")
        assert allowed.status_code == 307

    response = await api_client.get("/api/auth/telegram/start")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["retry-after"]) > 0
