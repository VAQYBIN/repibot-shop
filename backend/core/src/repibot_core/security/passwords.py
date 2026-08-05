"""Argon2id. Параметры — библиотечные значения по умолчанию.

Свои значения имеет смысл подбирать под конкретное железо; пока их нет,
библиотечные лучше выдуманных.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, VerifyMismatchError

_hasher = PasswordHasher()

# Хеш заведомо недостижимого пароля. Нужен, чтобы вход по неизвестному адресу
# занимал столько же времени, сколько вход с неверным паролем: иначе время
# ответа сообщает, зарегистрирован ли адрес.
DUMMY_HASH = _hasher.hash("несуществующий пароль для выравнивания времени")


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(stored: str | None, raw: str) -> bool:
    """Сверяет пароль. Отсутствующий хеш — это False, а не исключение."""
    try:
        return _hasher.verify(stored if stored is not None else DUMMY_HASH, raw)
    except (VerifyMismatchError, Argon2Error):
        return False


def needs_rehash(stored: str) -> bool:
    """Параметры Argon2 со временем растут; хеш пересчитывается при входе."""
    return _hasher.check_needs_rehash(stored)
