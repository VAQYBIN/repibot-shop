"""Единственный источник конфигурации. Всё остальное читает настройки отсюда."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Language = Literal["ru", "en"]

# Минимум для HMAC-SHA256 по RFC 7518 — 32 байта.
MIN_HMAC_SECRET_LENGTH = 32


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

    # Пустые реквизиты отключают оплату картой на конкретном развёртывании,
    # но неполная пара всегда означает ошибку конфигурации.
    yookassa_shop_id: str = ""
    yookassa_secret_key: SecretStr = SecretStr("")
    yookassa_api_base_url: str = "https://api.yookassa.ru/v3"
    # Привязку карты на нулевую сумму в боевом магазине подключает менеджер
    # YooKassa, поэтому по умолчанию она выключена: иначе кнопка приводила бы
    # пользователя к ошибке провайдера вместо честного «недоступно».
    yookassa_zero_amount_binding: bool = False
    referral_reward_percent: int = Field(default=10, ge=0, le=100)
    referral_reward_mode: Literal["first", "every"] = "first"
    yookassa_order_ttl_minutes: int = Field(default=30, gt=0)
    stars_order_ttl_minutes: int = Field(default=15, gt=0)
    # За 24 часа до срока, затем через 6 и 12 часов после предыдущей попытки.
    auto_renew_offsets_hours: tuple[int, int, int] = (-24, -18, -6)
    auto_renew_disable_after_final_failure: bool = True

    jwt_secret: SecretStr
    # Общий только с серверной частью Next. Подписанная им cookie — гейт показа
    # /admin, а не пропуск, который принимает API.
    admin_assertion_secret: SecretStr
    admin_assertion_ttl_seconds: int = Field(default=300, ge=60, le=900)
    encryption_key: SecretStr

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # Список идентификаторов Telegram. Роль поднимается при входе; удаление
    # идентификатора отсюда роль не снимает — понижение делается осознанно.
    # NoDecode отключает попытку pydantic-settings разобрать значение как JSON:
    # без неё строка "111, 222" падает с ошибкой парсинга раньше, чем успевает
    # отработать валидатор ниже.
    admin_telegram_ids: Annotated[tuple[int, ...], NoDecode] = ()

    # Пачка и параллельность разбора очереди. Сто и десять дают около десяти
    # тысяч сообщений в час — этого хватает базе в десятки тысяч человек в
    # день, когда у многих совпадает дата окончания.
    outbox_batch_size: int = Field(default=100, ge=1, le=1000)
    outbox_concurrency: int = Field(default=10, ge=1, le=50)

    # За сколько суток напоминать об окончании подписки. Список через запятую,
    # как у идентификаторов админов: NoDecode отключает разбор как JSON.
    # Каждый порог превращается в вид уведомления expiring_{days}, а вид обязан
    # быть в реестре и иметь тексты — поэтому значения не произвольные.
    expiry_reminder_days: Annotated[tuple[int, ...], NoDecode] = (3, 1)
    # Через сколько минут в pending напомнить о неоплаченном счёте. Меньше
    # получаса — торопить того, кто ещё не ушёл с формы оплаты.
    unpaid_invoice_after_minutes: int = Field(default=30, ge=5, le=1440)

    # Темп рассылки. Под лимитом Telegram в тридцать сообщений в секунду:
    # запас нужен, потому что рядом идут сервисные уведомления той же полосы.
    broadcast_rate_per_second: int = Field(default=25, ge=1, le=30)

    # Супергруппа с топиками, где персонал ведёт обращения. Пусто — поддержка
    # выключена целиком: стенд без супергруппы обязан подниматься и работать.
    support_chat_id: int | None = None
    # Одного открытого обращения мало: у человека одновременно может сломаться
    # оплата и доступ. Трёх хватает, дальше это уже поток, а не обращения.
    ticket_max_open: int = Field(default=3, ge=1, le=20)

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
        if len(value.get_secret_value()) < MIN_HMAC_SECRET_LENGTH:
            msg = (
                f"JWT_SECRET короче {MIN_HMAC_SECRET_LENGTH} символов; "
                "сгенерируйте: openssl rand -hex 32"
            )
            raise ValueError(msg)
        return value

    @field_validator("admin_assertion_secret")
    @classmethod
    def _admin_assertion_secret_is_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_HMAC_SECRET_LENGTH:
            msg = (
                f"ADMIN_ASSERTION_SECRET короче {MIN_HMAC_SECRET_LENGTH} символов; "
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

    @field_validator("expiry_reminder_days", mode="before")
    @classmethod
    def _split_reminder_days(cls, value: object) -> object:
        """Читает "3, 1" из окружения — по той же причине, что и список админов."""
        if not isinstance(value, str):
            return value
        return tuple(int(part) for part in value.split(",") if part.strip())

    @field_validator("yookassa_api_base_url")
    @classmethod
    def _yookassa_api_base_url_is_https(cls, value: str) -> str:
        normalized = value.rstrip("/")
        # Открытый HTTP развёртыванию недоступен. Единственное исключение —
        # заглушка внутри compose: её имя не разрешается за пределами сети, а
        # порт наружу не публикуется.
        if normalized == "http://yookassa-fake:3000/v3":
            return normalized
        if not normalized.startswith("https://"):
            msg = "YOOKASSA_API_BASE_URL должен начинаться с https://"
            raise ValueError(msg)
        return normalized

    @field_validator("auto_renew_offsets_hours")
    @classmethod
    def _auto_renew_offsets_are_ordered(cls, value: tuple[int, int, int]) -> tuple[int, int, int]:
        if value != tuple(sorted(value)):
            msg = "AUTO_RENEW_OFFSETS_HOURS должны идти по времени"
            raise ValueError(msg)
        return value

    def model_post_init(self, __context: object) -> None:
        has_shop_id = bool(self.yookassa_shop_id)
        has_secret = bool(self.yookassa_secret_key.get_secret_value())
        if has_shop_id != has_secret:
            msg = "YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY задаются вместе"
            raise ValueError(msg)
        if self.environment == "production" and self.yookassa_api_base_url.startswith("http://"):
            msg = "HTTP-заглушка YooKassa допустима только в local окружении"
            raise ValueError(msg)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированные настройки. Читаются один раз за жизнь процесса."""
    return Settings()
