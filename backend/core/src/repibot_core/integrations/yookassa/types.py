"""Нормализованные ответы YooKassa, не зависящие от тела webhook."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class YooKassaPaymentStatus(StrEnum):
    pending = "pending"
    waiting_for_capture = "waiting_for_capture"
    succeeded = "succeeded"
    canceled = "canceled"


class YooKassaBindingStatus(StrEnum):
    pending = "pending"
    active = "active"
    inactive = "inactive"


@dataclass(frozen=True, slots=True)
class YooKassaPayment:
    id: str
    status: YooKassaPaymentStatus
    amount_rub: Decimal
    currency: str
    confirmation_url: str | None
    payment_method_id: str | None = None
    # Ответ провайдера — единственное доказательство привязки: галочку
    # «запомнить карту» ставит плательщик на форме, а наш запрос о ней не
    # знает. Название приходит оттуда же и показывается как есть.
    payment_method_saved: bool = False
    payment_method_title: str | None = None


@dataclass(frozen=True, slots=True)
class YooKassaCardBinding:
    """Привязка карты без списания — отдельный ресурс провайдера."""

    id: str
    status: YooKassaBindingStatus
    saved: bool
    title: str | None
    confirmation_url: str | None
