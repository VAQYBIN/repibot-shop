"""Настройки обязаны падать на старте, а не при первом обращении к пустому полю."""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from repibot_core.settings import Settings, get_settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/repibot",
    "VALKEY_URL": "redis://localhost:6379/0",
    "BOT_TOKEN": "123456:test-token",
    "BOT_WEBHOOK_SECRET": "webhook-secret",
    "BOT_WEBHOOK_BASE_URL": "https://example.org",
    "REMNAWAVE_BASE_URL": "https://panel.example.org",
    "REMNAWAVE_TOKEN": "panel-token",
    # Длина не случайна: короткий ключ подписи настройки отвергают.
    "JWT_SECRET": "0123456789abcdef0123456789abcdef",
    "ENCRYPTION_KEY": "encryption-key",
    "PUBLIC_WEB_URL": "https://example.org",
    "PUBLIC_APP_URL": "https://example.org/app",
}


def _apply_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    """Ставит ровно указанное окружение, вычистив всё, что могло прийти от машины."""
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def _build(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    _apply_env(monkeypatch, {**REQUIRED_ENV, **overrides})
    return Settings(_env_file=None)


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _build(monkeypatch)

    assert settings.environment == "local"
    assert settings.default_language == "ru"
    assert settings.supported_languages == ("ru", "en")
    assert settings.bot_use_polling is False
    assert settings.database_url == REQUIRED_ENV["DATABASE_URL"]


def test_secrets_are_not_exposed_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Настройки попадают в логи целиком чаще, чем хотелось бы."""
    settings = _build(monkeypatch)

    assert "panel-token" not in repr(settings)
    assert "123456:test-token" not in repr(settings)
    assert settings.remnawave_token.get_secret_value() == "panel-token"


@pytest.mark.parametrize("missing", sorted(REQUIRED_ENV))
def test_missing_required_variable_fails_with_its_name(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    _apply_env(monkeypatch, {k: v for k, v in REQUIRED_ENV.items() if k != missing})

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)

    assert missing.lower() in str(exc.value)


def test_unsupported_default_language_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _build(monkeypatch, DEFAULT_LANGUAGE="de")


def test_short_jwt_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Слабый ключ подписи позволяет собрать токен с любым sub.

    Проверка на старте, а не строчка в документации: развёртывание с секретом
    вида «changeme» не должно доехать до приёма запросов.
    """
    with pytest.raises(ValidationError) as exc:
        _build(monkeypatch, JWT_SECRET="слишком короткий")

    assert "openssl rand -hex 32" in str(exc.value)


def test_admin_ids_parse_from_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Список админов задаётся строкой: JSON в .env читать неудобно человеку."""
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "111, 222")
    get_settings.cache_clear()

    assert get_settings().admin_telegram_ids == (111, 222)


def test_admin_ids_default_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_TELEGRAM_IDS", raising=False)
    get_settings.cache_clear()

    assert get_settings().admin_telegram_ids == ()


def test_token_lifetimes_have_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACCESS_TOKEN_TTL_MINUTES", raising=False)
    monkeypatch.delenv("REFRESH_TOKEN_TTL_DAYS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.access_token_ttl_minutes == 15
    assert settings.refresh_token_ttl_days == 30


def test_commerce_settings_have_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _build(monkeypatch)

    assert settings.yookassa_api_base_url == "https://api.yookassa.ru/v3"
    assert settings.referral_reward_percent == 10
    assert settings.referral_reward_mode == "first"
    assert settings.yookassa_order_ttl_minutes == 30
    assert settings.stars_order_ttl_minutes == 15
    assert settings.auto_renew_offsets_hours == (-24, 6, 12)
    assert settings.auto_renew_disable_after_final_failure is True


def test_e2e_yookassa_http_is_limited_to_its_compose_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Permitting arbitrary cleartext URLs would turn an E2E convenience into a payment risk."""
    settings = _build(
        monkeypatch,
        YOOKASSA_SHOP_ID="e2e-shop",
        YOOKASSA_SECRET_KEY="e2e-secret",
        YOOKASSA_API_BASE_URL="http://yookassa-fake:3000/v3",
    )

    assert settings.yookassa_api_base_url == "http://yookassa-fake:3000/v3"
    with pytest.raises(ValidationError):
        _build(monkeypatch, YOOKASSA_API_BASE_URL="http://payment-proxy.example/v3")
    with pytest.raises(ValidationError):
        _build(
            monkeypatch,
            ENVIRONMENT="production",
            YOOKASSA_API_BASE_URL="http://yookassa-fake:3000/v3",
        )


def test_invalid_referral_reward_settings_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _build(monkeypatch, REFERRAL_REWARD_PERCENT="-1")


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Настройки кэшируются на процесс, а тесты меняют окружение."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
