"""Юридические документы: соглашение, политика, оферта — что заведёт админ.

Набор имён не фиксирован: проект открытый, у каждого разворачивающего свой
перечень и своё юрлицо. Поэтому slug — обычное поле, а не перечисление.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class LegalDocument(TimestampMixin, Base):
    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint("slug", "locale", "version", name="uq_legal_documents_version"),
        # Черновик у пары ровно один. NULL в обычном уникальном индексе
        # Postgres не конфликтует сам с собой, поэтому условие вынесено в
        # частичный индекс — без него вторая правка молча завела бы второй
        # черновик, и «открыть черновик» перестало бы иметь единственный ответ.
        Index(
            "uq_legal_documents_single_draft",
            "slug",
            "locale",
            unique=True,
            postgresql_where=text("published_at IS NULL"),
        ),
        Index("ix_legal_documents_lookup", "slug", "locale", "version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64))
    locale: Mapped[str] = mapped_column(String(2))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Снятие с публикации не стирает текст: удалить условия, на которых
    # кто-то уже купил, — ровно то, ради чего версии и заводились.
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
