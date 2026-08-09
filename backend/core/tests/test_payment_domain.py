"""Чистые денежные расчёты не теряют копейки и не допускают некорректный ввод."""

from decimal import Decimal

import pytest

from repibot_core.domain.payments import quote_percent_discount, referral_reward_days


def test_quote_never_uses_float_and_rounds_to_kopecks() -> None:
    """Смена округления или float дала бы расхождение суммы с платёжным провайдером."""
    quote = quote_percent_discount(Decimal("299.00"), 15)

    assert quote.discount_rub == Decimal("44.85")
    assert quote.amount_due_rub == Decimal("254.15")


def test_referral_reward_is_at_least_one_day_for_positive_percent() -> None:
    """Малый процент от короткой покупки не должен исчезнуть при floor-округлении."""
    assert referral_reward_days(7, 1) == 1
    assert referral_reward_days(30, 10) == 3


@pytest.mark.parametrize(("days", "percent"), [(-1, 1), (1, -1)])
def test_referral_reward_rejects_negative_inputs(days: int, percent: int) -> None:
    """Отрицательная конфигурация или срок не должны превращаться в начисление."""
    with pytest.raises(ValueError):
        referral_reward_days(days, percent)
