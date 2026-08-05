"""Единственный источник конфигурации. Всё остальное читает настройки отсюда."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Language = Literal["ru", "en"]


class Settings(BaseSettings):
    """Конфигурация развёртывания.

    Поля без значения по умолчанию обязательны: их отсутствие валит процесс
    на старте с указанием имени переменной.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["local", "production"] = "local"

    database_url: str
    valkey_url: str

    bot_token: SecretStr
    bot_webhook_secret: SecretStr
    bot_webhook_base_url: str
    bot_use_polling: bool = False

    remnawave_base_url: str
    remnawave_token: SecretStr
    remnawave_timeout_seconds: float = 10.0
    # Именно попытки: три означает три запроса, а не один плюс три повтора.
    remnawave_max_attempts: int = 3

    jwt_secret: SecretStr
    encryption_key: SecretStr

    public_web_url: str
    public_app_url: str

    default_language: Language = "ru"
    supported_languages: tuple[Language, ...] = ("ru", "en")

    log_level: str = Field(default="INFO")

    @field_validator("default_language")
    @classmethod
    def _default_language_is_supported(cls, value: Language) -> Language:
        if value not in ("ru", "en"):
            msg = f"язык {value} не поддерживается"
            raise ValueError(msg)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированные настройки. Читаются один раз за жизнь процесса."""
    return Settings()  # type: ignore[call-arg]
