"""Пользователь. В этом подпроекте — минимальный каркас.

Поля почты, Telegram, роли и языка добавляются в подпроекте 1 отдельной миграцией.
"""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
