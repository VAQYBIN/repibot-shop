"""Подписка пользователя и журнал начислений."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin
from repibot_core.domain.subscriptions import SubscriptionState


class SubscriptionSource(StrEnum):
    trial = "trial"
    purchase = "purchase"
    gift = "gift"
    admin = "admin"


class SubscriptionEventType(StrEnum):
    trial = "trial"
    purchase = "purchase"
    renew = "renew"
    plan_change = "plan_change"
    bonus_days = "bonus_days"
    gift = "gift"
    expired = "expired"
    admin_grant = "admin_grant"
    admin_revoke = "admin_revoke"


class SubscriptionActor(StrEnum):
    user = "user"
    admin = "admin"
    system = "system"


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    # Крон истечения выбирает по статусу и дате — без индекса это полный проход
    # по таблице каждый час.
    __table_args__ = (Index("ix_subscriptions_expires_at", "status", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Одна подписка на пользователя: одна ссылка навсегда, как решено
    # архитектурой. Подарки добавляют дни, а не вторую строку.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))

    status: Mapped[SubscriptionState] = mapped_column(
        Enum(SubscriptionState, name="subscription_status", native_enum=True)
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    auto_renew_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[SubscriptionSource] = mapped_column(
        Enum(SubscriptionSource, name="subscription_source", native_enum=True)
    )
    # Цена и срок того права, которое уже лежит на аккаунте. При переходе на
    # другой платный тариф остаток переводится по этой зафиксированной цене,
    # а не по сегодняшней цене старого Plan.
    entitlement_price_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    entitlement_duration_days: Mapped[int] = mapped_column(Integer, default=0)


class SubscriptionEvent(Base):
    """Журнал начислений.

    Текущее состояние читается из subscriptions одним запросом, а разбор
    спорного случая — отсюда. Одно без другого не работает: состояние не
    помнит происхождения дней, журнал не отвечает, сколько осталось.
    """

    __tablename__ = "subscription_events"
    # Разбор случая — это «покажи историю пользователя по времени»: индекс
    # повторяет порядок такого запроса.
    __table_args__ = (
        Index("ix_subscription_events_user_id", "user_id", "created_at"),
        Index(
            "uq_subscription_events_origin_attempt_id",
            "origin_attempt_id",
            unique=True,
            postgresql_where=text("origin_attempt_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[SubscriptionEventType] = mapped_column(
        Enum(SubscriptionEventType, name="subscription_event_type", native_enum=True)
    )
    days_delta: Mapped[int] = mapped_column(Integer)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"))
    actor: Mapped[SubscriptionActor] = mapped_column(
        Enum(SubscriptionActor, name="subscription_actor", native_enum=True)
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    origin_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("payment_attempts.id", ondelete="SET NULL")
    )
    comment: Mapped[str | None] = mapped_column(String(512))
    # created_at объявлен явно, без TimestampMixin: у журнальной записи нет
    # момента изменения, а updated_at в неизменяемой таблице только вводит в
    # заблуждение. Значение проставляет сервис.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
