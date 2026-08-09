"""Значения по умолчанию для настроек подписок."""

from __future__ import annotations

from repibot_core.settings import Settings


def test_defaults_are_safe() -> None:
    settings = Settings()

    # Пустой секрет означает «вебхуки не настроены»: принимать неподписанные
    # события опаснее, чем не принимать никаких.
    assert settings.remnawave_webhook_secret.get_secret_value() == ""
    assert settings.remnawave_webhook_header == "x-remnawave-signature"
    # Синхронная попытка короче обычного таймаута клиента: пользователь ждёт
    # ответа, а надёжность обеспечивает очередь, а не терпение.
    assert settings.remnawave_provision_timeout_seconds == 3.0
    assert settings.panel_cache_ttl_seconds == 60
    assert settings.device_unlink_limit_per_day == 10
    assert settings.plan_change_keeps_remainder is True
    assert settings.reconcile_interval_hours == 6
