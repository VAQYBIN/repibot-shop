"""Выданные ступени лесенки возврата.

Ключом служит Telegram, если он привязан, и наш пользователь иначе. Причина
та же, что у trial_grants: флаг на аккаунте обходится удалением аккаунта и
повторной регистрацией, а почту накрутить тривиально.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, func, text
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class WinbackGrant(Base):
    __tablename__ = "winback_grants"
    __table_args__ = (
        # Два частичных индекса вместо одного составного: NULL в уникальном
        # индексе Postgres не конфликтует сам с собой, и общий индекс пропустил
        # бы вторую выдачу и по Telegram, и по аккаунту.
        Index(
            "uq_winback_grants_telegram",
            "telegram_id",
            "step",
            unique=True,
            postgresql_where=text("telegram_id IS NOT NULL"),
        ),
        Index(
            "uq_winback_grants_user",
            "user_id",
            "step",
            unique=True,
            postgresql_where=text("telegram_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    step: Mapped[int] = mapped_column(Integer)
    days: Mapped[int] = mapped_column(Integer, default=0)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
