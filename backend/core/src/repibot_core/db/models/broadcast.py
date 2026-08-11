"""Массовая рассылка — вторая полоса доставки.

Через общий outbox рассылка на пять тысяч человек заняла бы четыре часа и всё
это время держала бы за собой чек об оплате: очередь одна, порядок по времени
готовности. Поэтому у кампаний свои таблицы и своя задача.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class BroadcastStatus(StrEnum):
    draft = "draft"
    running = "running"
    canceled = "canceled"
    done = "done"


class RecipientStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Пустое значение допустимо: уволенного сотрудника удаляют, а история
    # рассылок остаётся — по ней разбирают, что и кому уходило. NOT NULL с
    # ondelete SET NULL противоречив, и удаление автора падало бы на нём.
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    segment: Mapped[str] = mapped_column(String(32))
    # По строке на язык, как у названий тарифов: рассылка уходит людям с
    # разной настройкой языка, и один текст на всех означает, что половина
    # получит чужой.
    title: Mapped[dict[str, str]] = mapped_column(JSONB)
    body: Mapped[dict[str, str]] = mapped_column(JSONB)
    status: Mapped[BroadcastStatus] = mapped_column(Enum(BroadcastStatus, name="broadcast_status"))
    planned_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BroadcastRecipient(Base):
    __tablename__ = "broadcast_recipients"
    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_recipients_person"),
        # По нему задача берёт следующую пачку: без индекса каждая пачка
        # обходила бы всю таблицу получателей кампании.
        Index("ix_broadcast_recipients_queue", "broadcast_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(16))
    # Адрес фиксируется вместе с аудиторией: смена почты во время рассылки не
    # должна превращать половину кампании в письма на два разных адреса.
    recipient: Mapped[str] = mapped_column(String(320))
    language: Mapped[str] = mapped_column(String(2))
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="broadcast_recipient_status")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(512))
