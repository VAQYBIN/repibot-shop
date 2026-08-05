"""Настройки обязаны падать на старте, а не при первом обращении к пустому полю."""

import pytest
from pydantic import ValidationError

from repibot_core.settings import Settings

REQUIRED_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/repibot",
    "VALKEY_URL": "redis://localhost:6379/0",
    "BOT_TOKEN": "123456:test-token",
    "BOT_WEBHOOK_SECRET": "webhook-secret",
    "BOT_WEBHOOK_BASE_URL": "https://example.org",
    "REMNAWAVE_BASE_URL": "https://panel.example.org",
    "REMNAWAVE_TOKEN": "panel-token",
    "JWT_SECRET": "jwt-secret",
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
    return Settings(_env_file=None)  # type: ignore[call-arg]


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
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert missing.lower() in str(exc.value)


def test_unsupported_default_language_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _build(monkeypatch, DEFAULT_LANGUAGE="de")
