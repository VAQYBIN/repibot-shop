"""Правила идентичности: почта, пароль, коды, сроки, отвязка способов входа.

Чистые функции без ввода-вывода. Всё, что здесь описано, проверяется тестами
без базы и сети — поэтому сюда и вынесено.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from repibot_core.db.models import TokenType

MIN_PASSWORD_LENGTH = 10

# Без 0/O, 1/I/L: код читают вслух и переписывают руками.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
REFERRAL_CODE_LENGTH = 8
LINK_CODE_LENGTH = 6

TOKEN_LIFETIMES: dict[TokenType, timedelta] = {
    TokenType.email_verify: timedelta(hours=24),
    TokenType.password_reset: timedelta(hours=1),
    TokenType.email_change: timedelta(hours=1),
}

LoginMethod = Literal["password", "telegram", "passkey"]


class PasswordPolicyError(ValueError):
    """Пароль не удовлетворяет требованиям."""


def normalize_email(raw: str) -> str:
    """Приводит адрес к каноническому виду.

    Регистр домена и локальной части для нас не значим, а хранение двух записей
    для одного человека значимо: адрес — уникальный ключ.
    """
    return raw.strip().lower()


def validate_password(password: str, *, email: str | None) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        msg = f"пароль короче {MIN_PASSWORD_LENGTH} символов"
        raise PasswordPolicyError(msg)
    if email is not None and password.strip().lower() == normalize_email(email):
        msg = "пароль совпадает с адресом почты"
        raise PasswordPolicyError(msg)


def _code(length: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def generate_referral_code() -> str:
    return _code(REFERRAL_CODE_LENGTH)


def generate_link_code() -> str:
    return _code(LINK_CODE_LENGTH)


@dataclass(frozen=True, slots=True)
class LoginMethods:
    """Способы, которыми пользователь может войти прямо сейчас."""

    has_password: bool
    has_telegram: bool
    passkey_count: int

    def count(self) -> int:
        return int(self.has_password) + int(self.has_telegram) + self.passkey_count


def can_unlink(methods: LoginMethods, method: LoginMethod) -> bool:
    """Можно ли снять способ входа, не заперев человека снаружи.

    Считаем не «сколько способов есть», а «сколько останется»: снятие пароля
    при двух passkey допустимо, снятие единственного Telegram — нет.
    """
    remaining = methods.count()
    if method == "password":
        remaining -= int(methods.has_password)
    elif method == "telegram":
        remaining -= int(methods.has_telegram)
    else:
        remaining -= 1 if methods.passkey_count else 0
    return remaining > 0
