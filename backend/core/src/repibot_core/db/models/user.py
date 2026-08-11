"""Пользователь: личность, способы входа, роль."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class UserRole(StrEnum):
    user = "user"
    support = "support"
    admin = "admin"


class UserStatus(StrEnum):
    active = "active"
    banned = "banned"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Почта и пароль допускают отсутствие: вошедший через Telegram не имеет ни
    # того, ни другого. Аккаунт существует, пока у него есть хотя бы один
    # способ входа — это правило живёт в domain.identity.can_unlink.
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_hash: Mapped[str | None] = mapped_column(String(255))

    # BigInteger: идентификаторы Telegram давно не влезают в 32 бита.
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))

    name: Mapped[str | None] = mapped_column(String(128))
    language: Mapped[str] = mapped_column(String(2), default="ru")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=True), default=UserRole.user
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", native_enum=True), default=UserStatus.active
    )

    # Хранится момент, а не флаг: при разборе жалобы важно, когда человек
    # отказался, — до рассылки или после неё.
    marketing_opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    referral_code: Mapped[str] = mapped_column(String(16), unique=True)
    referred_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Панель 3.2.1 адресует пользователя числом; поля uuid у него больше нет.
    # BigInteger с запасом: идентификатор растёт с каждым созданным в панели
    # пользователем, включая заведённых мимо нас.
    remnawave_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    remnawave_short_uuid: Mapped[str | None] = mapped_column(String(64))
    # Ссылка подписки приходит из панели и обновляется на каждом примирении.
    # Собирать её из REMNAWAVE_BASE_URL нельзя: публичный домен подписки
    # настраивается в панели отдельно, а revoke меняет shortUuid.
    remnawave_subscription_url: Mapped[str | None] = mapped_column(String(512))
