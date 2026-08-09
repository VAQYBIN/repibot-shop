"""Правила начисления дней. Без БД и сети."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from repibot_core.domain.subscriptions import (
    SubscriptionState,
    convert_remainder,
    extend,
    panel_username,
    resolve_state,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def test_username_is_short_and_allowed_by_panel() -> None:
    """Панель принимает 3–36 символов из букв, цифр, дефиса и подчёркивания."""
    assert panel_username(1) == "rp_1"
    assert panel_username(1_000_000) == "rp_lfls"


def test_extend_from_expiry_when_active() -> None:
    """Активная подписка продлевается от даты окончания: оплаченное не теряется."""
    expires = NOW + timedelta(days=5)
    assert extend(expires, NOW, 30) == expires + timedelta(days=30)


def test_extend_from_now_when_expired() -> None:
    """Истёкшая — от текущего момента, иначе покупка уходит в прошлое."""
    expires = NOW - timedelta(days=10)
    assert extend(expires, NOW, 30) == NOW + timedelta(days=30)


def test_extend_from_now_when_no_subscription() -> None:
    assert extend(None, NOW, 7) == NOW + timedelta(days=7)


def test_convert_remainder_scales_by_daily_price() -> None:
    """20 дней по 10 ₽/день — это 200 ₽, то есть 10 дней по 20 ₽/день."""
    days = convert_remainder(
        expires_at=NOW + timedelta(days=20),
        now=NOW,
        current_price_rub=Decimal("300.00"),
        current_duration_days=30,
        new_price_rub=Decimal("600.00"),
        new_duration_days=30,
    )
    assert days == 10


def test_convert_remainder_is_zero_for_expired() -> None:
    days = convert_remainder(
        expires_at=NOW - timedelta(days=1),
        now=NOW,
        current_price_rub=Decimal("300.00"),
        current_duration_days=30,
        new_price_rub=Decimal("300.00"),
        new_duration_days=30,
    )
    assert days == 0


def test_convert_remainder_rejects_free_plan() -> None:
    """Стоимость дня триала — ноль, делить на неё нечего."""
    with pytest.raises(ValueError, match="нулевая"):
        convert_remainder(
            expires_at=NOW + timedelta(days=5),
            now=NOW,
            current_price_rub=Decimal("300.00"),
            current_duration_days=30,
            new_price_rub=Decimal("0.00"),
            new_duration_days=7,
        )


@pytest.mark.parametrize(
    ("delta_days", "disabled", "provisioned", "is_trial", "expected"),
    [
        (10, False, True, False, SubscriptionState.active),
        (10, False, True, True, SubscriptionState.trial),
        (10, False, False, False, SubscriptionState.pending_provision),
        (10, True, True, False, SubscriptionState.disabled),
        (-1, False, True, True, SubscriptionState.expired),
        (-1, True, True, False, SubscriptionState.disabled),
    ],
)
def test_resolve_state(
    delta_days: int, disabled: bool, provisioned: bool, is_trial: bool, expected: SubscriptionState
) -> None:
    state = resolve_state(
        expires_at=NOW + timedelta(days=delta_days),
        now=NOW,
        disabled=disabled,
        provisioned=provisioned,
        is_trial=is_trial,
    )
    assert state is expected
