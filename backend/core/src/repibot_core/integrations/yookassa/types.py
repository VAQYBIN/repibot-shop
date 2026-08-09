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


@dataclass(frozen=True, slots=True)
class YooKassaPayment:
    id: str
    status: YooKassaPaymentStatus
    amount_rub: Decimal
    currency: str
    confirmation_url: str | None
