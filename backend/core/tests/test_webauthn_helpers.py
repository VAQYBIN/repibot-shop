"""Параметры проверяющей стороны и одноразовые challenge."""

from __future__ import annotations

import json

import pytest
from fakeredis.aioredis import FakeRedis
from webauthn.helpers import bytes_to_base64url

from repibot_core.security.webauthn import (
    challenge_from_response,
    credential_id_from_response,
    relying_party,
)
from repibot_core.services.challenges import ChallengeStore


def test_rp_id_is_the_bare_hostname() -> None:
    """RP ID — имя домена без схемы и порта: так требует спецификация WebAuthn."""
    party = relying_party("https://shop.example.org:8443")

    assert party.rp_id == "shop.example.org"
    assert party.origin == "https://shop.example.org:8443"


def test_localhost_keeps_its_port_in_origin() -> None:
    """Порт входит в origin, но не в RP ID: сквозные тесты идут на 8081."""
    party = relying_party("http://localhost:8081")

    assert party.rp_id == "localhost"
    assert party.origin == "http://localhost:8081"


def test_address_without_port_gives_origin_without_port() -> None:
    """Путь и стандартный порт в origin не попадают: браузер их тоже не шлёт."""
    assert relying_party("https://shop.example.org/app").origin == "https://shop.example.org"
    assert relying_party("https://shop.example.org:443").origin == "https://shop.example.org"


def test_address_without_scheme_is_rejected() -> None:
    with pytest.raises(ValueError, match="PUBLIC_WEB_URL"):
        relying_party("shop.example.org")


def test_challenge_is_read_from_client_data() -> None:
    client_data = json.dumps({"type": "webauthn.get", "challenge": bytes_to_base64url(b"abc")})
    credential = {
        "rawId": bytes_to_base64url(b"credential"),
        "response": {"clientDataJSON": bytes_to_base64url(client_data.encode())},
    }

    assert challenge_from_response(credential) == b"abc"
    assert credential_id_from_response(credential) == b"credential"


def test_broken_response_is_rejected_not_crashed() -> None:
    """Мусор в теле запроса — обычный отказ, а не пятисотка."""
    with pytest.raises(ValueError, match="ответ аутентификатора"):
        challenge_from_response({"response": {}})


async def test_challenge_is_accepted_once() -> None:
    """Повторное предъявление того же challenge — переигранный запрос."""
    store = ChallengeStore(FakeRedis())
    await store.remember("login", b"challenge")

    assert await store.take("login", b"challenge") == ""
    assert await store.take("login", b"challenge") is None


async def test_challenge_remembers_its_owner() -> None:
    store = ChallengeStore(FakeRedis())
    await store.remember("register", b"challenge", user_id=42)

    assert await store.take("register", b"challenge") == "42"


async def test_challenges_of_different_purposes_do_not_collide() -> None:
    """Challenge регистрации не принимается как challenge входа."""
    store = ChallengeStore(FakeRedis())
    await store.remember("register", b"challenge", user_id=7)

    assert await store.take("login", b"challenge") is None
    assert await store.take("register", b"challenge") == "7"


async def test_challenge_expires() -> None:
    """У записи есть срок жизни: забытый challenge не остаётся в Valkey навсегда."""
    redis = FakeRedis()
    store = ChallengeStore(redis, ttl_seconds=42)
    await store.remember("login", b"challenge")

    assert await redis.ttl("webauthn:login:Y2hhbGxlbmdl") == 42
