"""Единственный источник конфигурации. Всё остальное читает настройки отсюда."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Language = Literal["ru", "en"]

# Минимум для HMAC-SHA256 по RFC 7518 — 32 байта.
MIN_JWT_SECRET_LENGTH = 32


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

    # Выдаются в мини-приложении BotFather: Bot Settings → Web Login. Пустые
    # значения означают, что вход через Telegram в браузере не настроен —
    # кнопка тогда не показывается, а не ломается.
    telegram_oidc_client_id: str = ""
    telegram_oidc_client_secret: SecretStr = SecretStr("")

    remnawave_base_url: str
    remnawave_token: SecretStr
    remnawave_timeout_seconds: float = 10.0
    # Именно попытки: три означает три запроса, а не один плюс три повтора.
    remnawave_max_attempts: int = 3

    # Секрет и имя заголовка задаются на стороне панели. Имя вынесено в
    # настройку, потому что в схеме панели его нет: вебхуки исходящие, и
    # подтвердить заголовок можно только на живой панели.
    remnawave_webhook_secret: SecretStr = SecretStr("")
    remnawave_webhook_header: str = "x-remnawave-signature"
    # Синхронная попытка выдачи доступа. Короче обычного таймаута клиента:
    # надёжность даёт очередь, а не ожидание пользователя.
    remnawave_provision_timeout_seconds: float = 3.0

    # Минута — столько справочные данные панели (сквады, лимиты) переживают
    # без риска: админ, поменявший их только что, увидит правку почти сразу,
    # а список тарифов перестаёт дёргать панель на каждый показ витрины.
    panel_cache_ttl_seconds: int = 60
    # Десяти отвязок в сутки хватает при смене телефона и переустановке
    # системы; больше — это уже раздача подписки знакомым по кругу.
    device_unlink_limit_per_day: int = 10
    # Остаток при смене тарифа переезжает деньгами: иначе смена посреди
    # оплаченного месяца означала бы возврат, а его никто не делает.
    plan_change_keeps_remainder: bool = True
    # Сверка с панелью — страховка, а не основной путь: доступ выдаётся сразу
    # и добивается очередью. Четыре прогона в сутки закрывают расхождение
    # после сбоя панели, не превращая сверку в постоянную нагрузку.
    reconcile_interval_hours: int = 6

    jwt_secret: SecretStr
    encryption_key: SecretStr

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # Список идентификаторов Telegram. Роль поднимается при входе; удаление
    # идентификатора отсюда роль не снимает — понижение делается осознанно.
    # NoDecode отключает попытку pydantic-settings разобрать значение как JSON:
    # без неё строка "111, 222" падает с ошибкой парсинга раньше, чем успевает
    # отработать валидатор ниже.
    admin_telegram_ids: Annotated[tuple[int, ...], NoDecode] = ()

    email_sender: Literal["smtp", "log"] = "log"
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = "no-reply@example.org"
    smtp_starttls: bool = False

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

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_is_long_enough(cls, value: SecretStr) -> SecretStr:
        """HS256 подписывает ключом любой длины, но стойкость даёт только длинный.

        RFC 7518 требует для HMAC-SHA256 ключ не короче размера выхода хеша, то
        есть 32 байт. Короткий секрет подбирается перебором, и тогда подделать
        access-токен с любым `sub` — вопрос машинного времени. Проверка стоит
        здесь, а не в напоминании в документации: процесс со слабым ключом не
        должен стартовать вовсе.
        """
        if len(value.get_secret_value()) < MIN_JWT_SECRET_LENGTH:
            msg = (
                f"JWT_SECRET короче {MIN_JWT_SECRET_LENGTH} символов; "
                "сгенерируйте: openssl rand -hex 32"
            )
            raise ValueError(msg)
        return value

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _split_admin_ids(cls, value: object) -> object:
        """Читает "111, 222" из окружения.

        Pydantic ждёт для кортежа JSON-массив, а в .env человек пишет список
        через запятую. Пустая строка означает «админов нет».
        """
        if not isinstance(value, str):
            return value
        return tuple(int(part) for part in value.split(",") if part.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированные настройки. Читаются один раз за жизнь процесса."""
    return Settings()  # type: ignore[call-arg]
