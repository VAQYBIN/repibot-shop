"""Тариф: набор Internal Squad плюс лимиты и цена."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, Enum, Index, Integer, Numeric, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811 — не путать с uuid.UUID
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base, TimestampMixin


class TrafficResetStrategy(StrEnum):
    """Значения совпадают с панелью: они уходят в неё без преобразования."""

    NO_RESET = "NO_RESET"
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    MONTH_ROLLING = "MONTH_ROLLING"


class Plan(TimestampMixin, Base):
    __tablename__ = "plans"
    # Активный триальный тариф ровно один: иначе «какой триал выдать» — вопрос
    # без ответа. Условие индекса оставляет в нём только такие строки, и
    # уникальность по is_trial означает «строка ровно одна». Индекс объявлен и
    # в модели тоже — иначе autogenerate видит его в базе как лишний.
    __table_args__ = (
        Index(
            "uq_plans_single_active_trial",
            "is_trial",
            unique=True,
            postgresql_where=text("is_trial AND is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)

    # По локалям: {"ru": "…", "en": "…"}. Отдельные колонки под язык пришлось бы
    # добавлять миграцией на каждый новый язык.
    name: Mapped[dict[str, str]] = mapped_column(JSONB)
    description: Mapped[dict[str, str] | None] = mapped_column(JSONB)

    duration_days: Mapped[int] = mapped_column(Integer)
    # Numeric, а не float: YooKassa принимает сумму строкой «299.00», и
    # двоичная дробь здесь превращается в расхождение с чеком.
    price_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    price_stars: Mapped[int] = mapped_column(Integer)

    traffic_limit_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_reset_strategy: Mapped[TrafficResetStrategy] = mapped_column(
        Enum(TrafficResetStrategy, name="traffic_reset_strategy", native_enum=True),
        default=TrafficResetStrategy.NO_RESET,
    )
    hwid_device_limit: Mapped[int] = mapped_column(Integer, default=0)
    internal_squad_uuids: Mapped[list[str]] = mapped_column(ARRAY(PgUUID(as_uuid=False)))

    is_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
