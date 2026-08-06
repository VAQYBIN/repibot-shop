"""Хеширование паролей и работа с токенами."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from repibot_core.security.passwords import hash_password, verify_password
from repibot_core.security.tokens import (
    TokenInvalidError,
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_opaque_token,
)

# Не короче 32 символов: PyJWT предупреждает о слабом ключе для HS256, и это
# предупреждение не должно быть шумом, который перестают замечать.
SECRET = "0123456789abcdef0123456789abcdef"


def test_password_round_trip() -> None:
    stored = hash_password("совершенно обычный пароль")

    assert stored != "совершенно обычный пароль"
    assert verify_password(stored, "совершенно обычный пароль") is True
    assert verify_password(stored, "другой пароль") is False


def test_verify_password_handles_missing_hash() -> None:
    """У вошедшего через Telegram пароля нет.

    Проверка обязана вернуть False, а не упасть — иначе форма входа отвечает
    500 и заодно сообщает, что такой аккаунт существует.
    """
    assert verify_password(None, "любой пароль") is False


def test_access_token_round_trip() -> None:
    session_id = uuid4()

    token = create_access_token(42, session_id, secret=SECRET, ttl_minutes=15)
    claims = decode_access_token(token, secret=SECRET)

    assert claims.user_id == 42
    assert claims.session_id == session_id


def test_expired_access_token_is_rejected() -> None:
    token = create_access_token(
        42,
        uuid4(),
        secret=SECRET,
        ttl_minutes=15,
        now=datetime.now(UTC) - timedelta(hours=1),
    )

    with pytest.raises(TokenInvalidError):
        decode_access_token(token, secret=SECRET)


def test_token_signed_with_another_secret_is_rejected() -> None:
    token = create_access_token(
        42, uuid4(), secret="fedcba9876543210fedcba9876543210", ttl_minutes=15
    )

    with pytest.raises(TokenInvalidError):
        decode_access_token(token, secret=SECRET)


def test_garbage_is_rejected() -> None:
    with pytest.raises(TokenInvalidError):
        decode_access_token("не токен вовсе", secret=SECRET)


def test_opaque_tokens_are_unique_and_hashed() -> None:
    tokens = {generate_opaque_token() for _ in range(20)}

    assert len(tokens) == 20
    sample = tokens.pop()
    assert hash_opaque_token(sample) == hash_opaque_token(sample)
    assert len(hash_opaque_token(sample)) == 64
    assert hash_opaque_token(sample) != sample
