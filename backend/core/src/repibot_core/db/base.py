"""Декларативная база и общие примеси."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Общий предок всех моделей."""


class TimestampMixin:
    """Отметки создания и изменения.

    created_at проставляет база: server_default выполняется в самом INSERT,
    и значение появится даже при вставке в обход ORM.

    updated_at ставит SQLAlchemy — onupdate добавляет столбец в UPDATE, который
    она собирает сама. Обновление напрямую (SQL из миграции, ручной UPDATE
    в psql) отметку не тронет. Понадобится строгая гарантия — понадобится
    триггер на стороне базы.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
