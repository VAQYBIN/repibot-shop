"""Одноразовые токены: подтверждение почты, сброс пароля, смена почты."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class TokenType(StrEnum):
    email_verify = "email_verify"
    password_reset = "password_reset"  # noqa: S105 — это назначение токена, а не пароль
    email_change = "email_change"


class OneTimeToken(TimestampMixin, Base):
    __tablename__ = "one_time_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[TokenType] = mapped_column(Enum(TokenType, name="one_time_token_type"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # В базе только хеш: журнал запросов, дамп или доступ к базе не должны
    # давать возможность подтвердить чужую почту.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
