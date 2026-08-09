"""Входящие вебхуки: приняли, сохранили, обработали ровно один раз."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class WebhookSource(StrEnum):
    remnawave = "remnawave"
    yookassa = "yookassa"


class WebhookEvent(Base):
    """Журнал принятых событий.

    Тело сохраняется целиком: разбор спорного случая через неделю невозможен,
    если у нас осталась только наша интерпретация чужого сообщения.
    """

    __tablename__ = "webhook_events"
    # Идемпотентность держит база: две одновременные доставки одного события
    # проходят проверку «принимали ли» обе, и без ограничения в схеме событие
    # обработается дважды. Источник входит в ключ — идентификаторы у панели и
    # платёжного шлюза свои, и совпадение строк дублем не является.
    __table_args__ = (UniqueConstraint("source", "event_id", name="uq_webhook_events_source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[WebhookSource] = mapped_column(
        Enum(WebhookSource, name="webhook_source", native_enum=True)
    )
    # Панель своего идентификатора события не присылает, поэтому он собирается
    # из события, отметки времени и идентификатора пользователя.
    event_id: Mapped[str] = mapped_column(String(255))
    event: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Пустое значение означает «принято, но ещё не обработано»: по нему видно,
    # что осталось разобрать после сбоя обработчика.
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
