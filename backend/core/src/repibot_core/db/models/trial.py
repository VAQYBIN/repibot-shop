"""Выданные триалы. Живут отдельно от пользователя и переживают его удаление."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class TrialGrant(Base):
    """Ключ — идентификатор Telegram, а не наш пользователь.

    Флаг на самом пользователе обходится удалением аккаунта и повторной
    регистрацией. Почту накрутить тривиально, поэтому и она ключом не годится.
    """

    __tablename__ = "trial_grants"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
