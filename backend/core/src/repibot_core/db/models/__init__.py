"""Импорт всех моделей — Alembic должен видеть их в метаданных."""

from repibot_core.db.models.audit import AuditLog
from repibot_core.db.models.commerce import (
    CardBinding,
    CardBindingStatus,
    GiftVoucher,
    NotificationDelivery,
    Order,
    OrderPurpose,
    OrderStatus,
    PaymentAttempt,
    PaymentProvider,
    PaymentStatus,
    PromoCode,
    PromoReservation,
    ReferralReward,
    SavedPaymentMethod,
)
from repibot_core.db.models.one_time_token import OneTimeToken, TokenType
from repibot_core.db.models.outbox import OutboxMessage
from repibot_core.db.models.passkey import PasskeyCredential
from repibot_core.db.models.plan import Plan, TrafficResetStrategy
from repibot_core.db.models.reconciliation import FindingAction, ReconciliationFinding
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
from repibot_core.db.models.webhook import WebhookEvent, WebhookSource

__all__ = [
    "AuditLog",
    "CardBinding",
    "CardBindingStatus",
    "FindingAction",
    "GiftVoucher",
    "NotificationDelivery",
    "OneTimeToken",
    "Order",
    "OrderPurpose",
    "OrderStatus",
    "OutboxMessage",
    "PasskeyCredential",
    "PaymentAttempt",
    "PaymentProvider",
    "PaymentStatus",
    "Plan",
    "PromoCode",
    "PromoReservation",
    "ReconciliationFinding",
    "ReferralReward",
    "SavedPaymentMethod",
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
    "WebhookEvent",
    "WebhookSource",
]
