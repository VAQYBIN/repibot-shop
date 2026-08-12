"""Обращения в поддержку.

Переписка живёт здесь, а не в Telegram: у половины плательщиков Telegram не
привязан, и топик супергруппы для них — рабочее место персонала, а не канал
связи.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class TicketStatus(StrEnum):
    """Чьего хода ждёт обращение. Это всё, что нужно и очереди, и человеку."""

    waiting_staff = "waiting_staff"
    waiting_user = "waiting_user"
    closed = "closed"


class TicketAuthor(StrEnum):
    """Кто написал. `system` — наши же отметки вроде «обращение закрыто»."""

    user = "user"
    staff = "staff"
    system = "system"


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        # Очередь персонала — «что ждёт ответа дольше всех».
        Index("ix_tickets_queue", "status", "last_user_message_at"),
        Index("ix_tickets_user", "user_id", "created_at"),
        # Ответ сотрудника ищется по номеру топика через scalar(): второй
        # тикет с тем же номером молча увёл бы ответ чужому человеку.
        # Пустое поле при этом обычное дело — топик появляется после
        # создания обращения, поэтому индекс частичный.
        Index(
            "uq_tickets_topic",
            "telegram_topic_id",
            unique=True,
            postgresql_where=text("telegram_topic_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus, name="ticket_status"))
    subject: Mapped[str] = mapped_column(String(120))
    # Появляется после того, как топик создан в супергруппе. До этого момента
    # тикет уже существует: терять обращение из-за недоступного Telegram нельзя.
    telegram_topic_id: Mapped[int | None] = mapped_column(Integer)
    # Метка состояния, которая сейчас стоит в названии темы. Пустая говорит
    # сразу о двух вещах: тема ещё не помечена и карточка собеседника в неё не
    # уходила — второго признака не нужно, они появляются вместе.
    topic_status_mark: Mapped[TicketStatus | None] = mapped_column(
        Enum(TicketStatus, name="ticket_status")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_user_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_staff_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (Index("ix_ticket_messages_thread", "ticket_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    author_kind: Mapped[TicketAuthor] = mapped_column(Enum(TicketAuthor, name="ticket_author"))
    # У сотрудника, отвечающего из топика, нашего аккаунта может не быть.
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    body: Mapped[str] = mapped_column(Text)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
