"""Детерминированные расчёты, которые входят в коммерческий снимок заказа."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

KOPECK = Decimal("0.01")
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class Money:
    """Рублёвая сумма, нормализованная до копеек без участия float."""

    rub: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.rub, Decimal):
            msg = "сумма должна быть Decimal"
            raise TypeError(msg)
        if self.rub < 0:
            msg = "сумма не может быть отрицательной"
            raise ValueError(msg)
        object.__setattr__(self, "rub", self.rub.quantize(KOPECK, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class DiscountQuote:
    """Снимок скидки и итоговой суммы для заказа."""

    discount_rub: Decimal
    amount_due_rub: Decimal


def quote_percent_discount(gross_rub: Decimal, percent: int) -> DiscountQuote:
    """Возвращает скидку в копейках и сумму к оплате.

    Процент передаётся целым числом, потому что промокод не бывает «на 12.5%».
    """
    gross = Money(gross_rub).rub
    if not 0 <= percent <= 100:
        msg = "процент скидки должен быть от 0 до 100"
        raise ValueError(msg)
    discount = (gross * Decimal(percent) / HUNDRED).quantize(KOPECK, rounding=ROUND_HALF_UP)
    return DiscountQuote(discount_rub=discount, amount_due_rub=gross - discount)


def referral_reward_days(purchased_days: int, percent: int) -> int:
    """Начисляет рефереру дни по целочисленной формуле из коммерческих правил."""
    if purchased_days < 0 or percent < 0:
        msg = "дни и процент реферальной награды не могут быть отрицательными"
        raise ValueError(msg)
    if purchased_days == 0 or percent == 0:
        return 0
    return max(1, purchased_days * percent // 100)
