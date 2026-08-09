"""Неизменяемые коммерческие заказы и обращения к платёжным провайдерам."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class OrderPurpose(StrEnum):
    purchase = "purchase"
    renew = "renew"
    gift = "gift"


class OrderStatus(StrEnum):
    pending = "pending"
    fulfilled = "fulfilled"
    expired = "expired"
    canceled = "canceled"
    refunded = "refunded"


class PaymentProvider(StrEnum):
    yookassa = "yookassa"
    stars = "stars"


class PaymentStatus(StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    canceled = "canceled"
    failed = "failed"


class PromoCode(TimestampMixin, Base):
    """Настраиваемая администратором скидка для ручной покупки или продления."""

    __tablename__ = "promo_codes"
    __table_args__ = (
        CheckConstraint("percent_off >= 0 AND percent_off <= 100", name="ck_promos_percent_range"),
        CheckConstraint("bonus_days >= 0", name="ck_promos_bonus_nonnegative"),
        CheckConstraint("max_uses IS NULL OR max_uses > 0", name="ck_promos_max_uses_positive"),
        CheckConstraint(
            "per_user_limit IS NULL OR per_user_limit > 0", name="ck_promos_user_limit_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    percent_off: Mapped[int] = mapped_column(Integer, default=0)
    bonus_days: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    per_user_limit: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Order(TimestampMixin, Base):
    """Заказ фиксирует тариф и цену на момент намерения оплатить."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("user_id", "client_key", name="uq_orders_user_client_key"),
        CheckConstraint("duration_days_snapshot > 0", name="ck_orders_duration_positive"),
        CheckConstraint("price_rub_snapshot >= 0", name="ck_orders_price_nonnegative"),
        CheckConstraint("price_stars_snapshot >= 0", name="ck_orders_stars_nonnegative"),
        CheckConstraint("gross_rub >= 0", name="ck_orders_gross_nonnegative"),
        CheckConstraint("discount_rub >= 0", name="ck_orders_discount_nonnegative"),
        CheckConstraint("amount_due_rub >= 0", name="ck_orders_due_nonnegative"),
        CheckConstraint("amount_due_rub = gross_rub - discount_rub", name="ck_orders_due_matches"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[OrderPurpose] = mapped_column(
        Enum(OrderPurpose, name="order_purpose", native_enum=True)
    )
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))

    plan_code_snapshot: Mapped[str] = mapped_column(String(32))
    plan_name_snapshot: Mapped[dict[str, str]] = mapped_column(JSONB)
    duration_days_snapshot: Mapped[int] = mapped_column(Integer)
    price_rub_snapshot: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_stars_snapshot: Mapped[int] = mapped_column(Integer)
    gross_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    discount_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    amount_due_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    # Таблица промокодов появится со своим сервисом позже; до тех пор это
    # намеренно не FK, чтобы коммерческий фундамент не зависел от неё.
    promo_code_id: Mapped[int | None] = mapped_column(Integer)
    client_key: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", native_enum=True), default=OrderStatus.pending
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentAttempt(TimestampMixin, Base):
    """Одна попытка обращения к конкретному платёжному провайдеру."""

    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint(
            "order_id", "provider", "attempt_no", name="uq_attempts_order_provider_no"
        ),
        UniqueConstraint("provider", "provider_key", name="uq_attempts_provider_key"),
        UniqueConstraint("provider", "provider_payment_id", name="uq_attempts_provider_payment_id"),
        CheckConstraint("attempt_no > 0", name="ck_attempts_number_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, name="payment_provider", native_enum=True)
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    provider_key: Mapped[str] = mapped_column(String(128))
    handoff_token: Mapped[str | None] = mapped_column(String(128), unique=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=True), default=PaymentStatus.pending
    )
    verified_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PromoReservation(Base):
    """Зарезервированное применение промокода; правила резервирования — в сервисе."""

    __tablename__ = "promo_reservations"
    __table_args__ = (UniqueConstraint("order_id", name="uq_promo_reservations_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    promo_code_id: Mapped[int] = mapped_column(ForeignKey("promo_codes.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Legacy consumed reservations intentionally retain NULL after migration 0009:
    # their paid entitlement is already final. Every new pending reservation stores an int.
    bonus_days_snapshot: Mapped[int | None] = mapped_column(Integer)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GiftVoucher(Base):
    """Одноразовый ваучер, возникающий из успешно оплаченного gift-заказа."""

    __tablename__ = "gift_vouchers"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_gift_vouchers_order"),
        UniqueConstraint("code", name="uq_gift_vouchers_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64))
    purchased_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    redeemed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class ReferralReward(Base):
    """Аудируемая награда рефереру с единственным коммерческим источником."""

    __tablename__ = "referral_rewards"
    __table_args__ = (
        UniqueConstraint("origin_order_id", name="uq_referral_rewards_origin_order"),
        CheckConstraint("days > 0", name="ck_referral_rewards_days_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    referee_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    origin_order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    days: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(Base):
    """Дедуплицированное намерение отправить уведомление о заказе."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("order_id", "kind", "channel", name="uq_notification_deliveries_dedup"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
