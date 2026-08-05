"""Импорт всех моделей — Alembic должен видеть их в метаданных."""

from repibot_core.db.models.audit import AuditLog
from repibot_core.db.models.one_time_token import OneTimeToken, TokenType
from repibot_core.db.models.outbox import OutboxMessage
from repibot_core.db.models.session import Session
from repibot_core.db.models.user import User, UserRole, UserStatus

__all__ = [
    "AuditLog",
    "OneTimeToken",
    "OutboxMessage",
    "Session",
    "TokenType",
    "User",
    "UserRole",
    "UserStatus",
]
