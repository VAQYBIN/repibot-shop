"""Общие типы способов входа."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


class AuthError(Exception):
    """Ошибка входа, о которой клиенту сообщается кодом.

    Код совпадает с тем, что уходит в теле ответа API: перевод кода в фразу —
    дело фронтенда, а выбор статуса — дело роутера.
    """

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """Результат работы одного способа входа: кто это.

    Способ входа не выдаёт токенов и не проверяет статус — только опознаёт.
    """

    user_id: int


@dataclass(frozen=True, slots=True)
class IssuedSession:
    access_token: str
    refresh_token: str | None
    session_id: UUID
    access_expires_in: int
    refresh_expires_at: datetime | None
    # The router uses this only to mint/clear the short-lived Next route gate.
    # API authorization always reloads the role through PrincipalCache.
    is_admin: bool
