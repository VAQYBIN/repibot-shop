"""Правила идентичности. Ни базы, ни сети — только арифметика и строки."""

from __future__ import annotations

from datetime import timedelta

import pytest

from repibot_core.db.models import TokenType
from repibot_core.domain.identity import (
    TOKEN_LIFETIMES,
    LoginMethods,
    PasswordPolicyError,
    can_unlink,
    generate_link_code,
    generate_referral_code,
    normalize_email,
    validate_password,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("User@Example.ORG", "user@example.org"),
        ("  user@example.org  ", "user@example.org"),
    ],
)
def test_email_is_normalized(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


def test_password_shorter_than_ten_is_rejected() -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password("short1234", email=None)


def test_password_equal_to_email_is_rejected() -> None:
    """Пароль, равный адресу, ломает единственную защиту при утечке базы."""
    with pytest.raises(PasswordPolicyError):
        validate_password("user@example.org", email="user@example.org")


def test_long_password_is_accepted() -> None:
    validate_password("совершенно обычный пароль", email="user@example.org")


def test_referral_code_avoids_confusable_characters() -> None:
    """Код диктуют голосом и переписывают руками: 0/O и 1/I/L там не место."""
    code = generate_referral_code()

    assert len(code) == 8
    assert set(code) <= set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")


def test_codes_are_not_repeated() -> None:
    assert len({generate_referral_code() for _ in range(50)}) == 50
    assert len({generate_link_code() for _ in range(50)}) == 50


def test_token_lifetimes_match_the_spec() -> None:
    assert TOKEN_LIFETIMES[TokenType.email_verify] == timedelta(hours=24)
    assert TOKEN_LIFETIMES[TokenType.password_reset] == timedelta(hours=1)
    assert TOKEN_LIFETIMES[TokenType.email_change] == timedelta(hours=1)


def test_last_login_method_cannot_be_unlinked() -> None:
    only_telegram = LoginMethods(has_password=False, has_telegram=True, passkey_count=0)

    assert can_unlink(only_telegram, "telegram") is False


def test_method_can_be_unlinked_when_another_remains() -> None:
    both = LoginMethods(has_password=True, has_telegram=True, passkey_count=0)

    assert can_unlink(both, "telegram") is True
    assert can_unlink(both, "password") is True


def test_last_passkey_cannot_be_unlinked_without_password() -> None:
    single_passkey = LoginMethods(has_password=False, has_telegram=False, passkey_count=1)

    assert can_unlink(single_passkey, "passkey") is False
