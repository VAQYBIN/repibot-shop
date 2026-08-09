"""Правила подписки: сдвиг даты, конвертация остатка, состояние.

Чистые функции без БД и сети. Дату окончания двигает только этот модуль —
чтобы правило продления было записано ровно один раз и совпадало у бота,
MiniApp и веба.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
USERNAME_PREFIX = "rp_"


class SubscriptionState(StrEnum):
    trial = "trial"
    active = "active"
    expired = "expired"
    disabled = "disabled"
    pending_provision = "pending_provision"


def panel_username(user_id: int) -> str:
    """Имя пользователя в панели: `rp_` и наш идентификатор в base36.

    Панель ограничивает имя 36 символами и алфавитом без знаков препинания.
    base36 держит имя коротким и обратимым: по нему пользователь находится
    через resolve, если мы потеряли числовой идентификатор панели.
    """
    if user_id <= 0:
        msg = "идентификатор пользователя должен быть положительным"
        raise ValueError(msg)

    digits = ""
    value = user_id
    while value:
        value, remainder = divmod(value, len(ALPHABET))
        digits = ALPHABET[remainder] + digits
    return f"{USERNAME_PREFIX}{digits}"


def extend(expires_at: datetime | None, now: datetime, days: int) -> datetime:
    """Новая дата окончания после начисления дней.

    Активная подписка сдвигается от своей даты окончания, истёкшая и
    отсутствующая — от текущего момента. Иначе продление за день до конца
    съедало бы оплаченный остаток.
    """
    if days <= 0:
        msg = "число дней должно быть положительным"
        raise ValueError(msg)
    base = expires_at if expires_at is not None and expires_at > now else now
    return base + timedelta(days=days)


def convert_remainder(
    *,
    expires_at: datetime,
    now: datetime,
    current_price_rub: Decimal,
    current_duration_days: int,
    new_price_rub: Decimal,
    new_duration_days: int,
) -> int:
    """Остаток текущего тарифа в днях нового.

    Считается через стоимость дня: остаток превращается в деньги по цене дня
    текущего тарифа и делится на цену дня нового. Возвраты при смене тарифа
    тогда не нужны — оплаченное переезжает целиком.

    Дробный день отбрасывается: округление вверх позволяло бы бесконечно
    доливать время переключением туда-обратно.
    """
    if new_price_rub <= 0 or new_duration_days <= 0:
        msg = "у нового тарифа нулевая стоимость дня — конвертировать не во что"
        raise ValueError(msg)

    remaining = (expires_at - now).total_seconds() / timedelta(days=1).total_seconds()
    if remaining <= 0:
        return 0

    current_daily = current_price_rub / current_duration_days
    new_daily = new_price_rub / new_duration_days
    return int(Decimal(remaining) * current_daily / new_daily)


def resolve_state(
    *,
    expires_at: datetime,
    now: datetime,
    disabled: bool,
    provisioned: bool,
    is_trial: bool,
) -> SubscriptionState:
    """Состояние подписки одним правилом на все интерфейсы.

    Порядок проверок важен: снятый админом доступ виден и при живой дате,
    а невыданный доступ — не то же самое, что истёкший.
    """
    if disabled:
        return SubscriptionState.disabled
    if not provisioned:
        return SubscriptionState.pending_provision
    if expires_at <= now:
        return SubscriptionState.expired
    return SubscriptionState.trial if is_trial else SubscriptionState.active
