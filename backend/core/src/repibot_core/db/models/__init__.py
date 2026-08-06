"""Импорт всех моделей — Alembic должен видеть их в метаданных."""

from repibot_core.db.models.audit import AuditLog
from repibot_core.db.models.one_time_token import OneTimeToken, TokenType
from repibot_core.db.models.outbox import OutboxMessage
from repibot_core.db.models.passkey import PasskeyCredential
from repibot_core.db.models.plan import Plan, TrafficResetStrategy
from repibot_core.db.models.session import Session
from repibot_core.db.models.subscription import (
    Subscription,
    SubscriptionActor,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionSource,
)
from repibot_core.db.models.trial import TrialGrant
from repibot_core.db.models.user import User, UserRole, UserStatus

__all__ = [
    "AuditLog",
    "OneTimeToken",
    "OutboxMessage",
    "PasskeyCredential",
    "Plan",
    "Session",
    "Subscription",
    "SubscriptionActor",
    "SubscriptionEvent",
    "SubscriptionEventType",
    "SubscriptionSource",
    "TokenType",
    "TrafficResetStrategy",
    "TrialGrant",
    "User",
    "UserRole",
    "UserStatus",
]
