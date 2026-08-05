"""Импорт всех моделей — Alembic должен видеть их в метаданных."""

from repibot_core.db.models.user import User

__all__ = ["User"]
