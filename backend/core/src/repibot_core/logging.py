"""Структурные логи в JSON с идентификатором запроса и маскированием секретов."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"bot\d+:[A-Za-z0-9_-]{30,}"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    re.compile(r"(?i)(\"?(?:token|secret|password|api_key)\"?\s*[:=]\s*\"?)[^\s\",}]+"),
    # Пароль в адресе подключения: SQLAlchemy своё имя пользователя и пароль
    # прячет сама, но redis, SMTP и произвольные строки в логах — нет.
    re.compile(r"(?i)([a-z][a-z0-9+.-]*://[^:/?#\s@]+:)[^@/\s]+(?=@)"),
)


def set_request_id(value: str) -> None:
    """Устанавливает идентификатор запроса для текущего контекста выполнения."""
    request_id_var.set(value)


def mask(text: str) -> str:
    """Вырезает известные виды секретов из произвольного текста."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "***", text)
    return text


class SecretFilter(logging.Filter):
    """Вырезает токены и пароли из текста сообщения.

    Это последний рубеж, а не замена дисциплине: логировать секреты осознанно
    всё равно нельзя. Но чужие библиотеки об этом не знают.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = mask(message)
        if masked != message:
            record.msg = masked
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """Одна строка JSON на запись."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": mask(record.getMessage()),
        }
        # Явно переданный в extra идентификатор важнее контекстного: обработчик
        # ошибки 500 работает вне контекста запроса и передаёт его сам.
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id
        if record.exc_info:
            # Трассировка собирается здесь, а не в фильтре: SecretFilter правит
            # только текст сообщения и до неё не дотягивается.
            payload["exception"] = mask(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Настраивает корневой логгер. Вызывается один раз при старте процесса."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    for noisy in ("httpx", "httpcore", "aiogram.event"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
