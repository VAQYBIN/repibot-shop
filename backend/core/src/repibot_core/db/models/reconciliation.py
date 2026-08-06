"""Расхождения между нашей БД и панелью."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811 — не путать с uuid.UUID
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class FindingAction(StrEnum):
    fixed = "fixed"
    skipped = "skipped"


class ReconciliationFinding(Base):
    """Что разошлось, каким было у нас и в панели, что с этим сделали.

    Расхождение почти всегда означает ручную правку админа в панели, и о ней
    надо знать. Поэтому запись делается всегда, а не только при отказе.
    """

    __tablename__ = "reconciliation_findings"
    # Отчёт читается прогоном целиком, а не построчно: индекс повторяет порядок
    # такого запроса — выбрать прогон и пройти его строки по возрастанию id.
    __table_args__ = (Index("ix_reconciliation_findings_run", "run_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Идентификатор прогона: без него отчёт превращается в ленту без границ,
    # и «что нашла последняя сверка» становится вопросом с догадкой.
    run_id: Mapped[str] = mapped_column(PgUUID(as_uuid=False))
    # Ссылка гаснет вместе с аккаунтом, а строка остаётся: отчёт о прошлой
    # сверке не должен исчезать из-за удаления пользователя.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    field: Mapped[str] = mapped_column(String(64))
    ours: Mapped[str | None] = mapped_column(String(512))
    theirs: Mapped[str | None] = mapped_column(String(512))
    action: Mapped[FindingAction] = mapped_column(
        Enum(FindingAction, name="reconciliation_action", native_enum=True)
    )
    # created_at объявлен явно, без TimestampMixin: запись неизменяемая, и
    # updated_at в ней только вводил бы в заблуждение.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
