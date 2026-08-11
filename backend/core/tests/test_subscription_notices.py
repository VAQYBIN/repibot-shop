"""Напоминания о судьбе подписки."""

from __future__ import annotations

import pytest

from repibot_core.i18n import translate
from repibot_core.services.notifications import resolve_kind
from repibot_core.settings import Settings


def _settings(**overrides: object) -> Settings:
    """Настройки поверх тестового окружения.

    Конструктор читает те же переменные, что и боевой процесс: собирать их
    здесь заново значит проверять сборку, а не разбор значения.
    """
    return Settings(**overrides)  # type: ignore[arg-type]


def test_reminder_days_are_read_from_a_comma_separated_string() -> None:
    """В .env человек пишет список через запятую, а не JSON-массив."""
    assert _settings(EXPIRY_REMINDER_DAYS="3, 1").expiry_reminder_days == (3, 1)


def test_every_threshold_has_a_registered_kind_and_texts() -> None:
    """Порог из .env превращается в вид уведомления, а вид нужно объявить.

    Без этой проверки строка EXPIRY_REMINDER_DAYS=7 роняла бы крон на живом
    стенде: resolve_kind не знает вида expiring_7, а translate — его текстов.
    Поэтому пороги не произвольные, и добавление третьего — это задача.
    """
    for days in _settings().expiry_reminder_days:
        kind = resolve_kind(f"expiring_{days}")
        assert translate("ru", f"{kind.text_key}.bot", plan="Месяц", date="01.01.2026")
        assert translate("en", f"{kind.text_key}.bot", plan="Month", date="01.01.2026")


@pytest.mark.parametrize("value", ["4", "0", "10"])
def test_unregistered_threshold_is_caught_here_and_not_in_production(value: str) -> None:
    """Проверка выше должна ловить чужой порог, а не пропускать его молча."""
    with pytest.raises(KeyError):
        resolve_kind(f"expiring_{value}")
