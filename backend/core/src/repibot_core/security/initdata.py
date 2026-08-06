"""Проверка initData из Telegram MiniApp.

Схема задана Telegram: строка проверки — отсортированные пары ключ=значение
через перевод строки, ключ — HMAC от токена бота на строке "WebAppData".
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """initData отсутствует, подделан или устарел."""


@dataclass(frozen=True, slots=True)
class TelegramUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    language_code: str | None


def parse_init_data(
    raw: str, *, bot_token: str, max_age: timedelta, now: datetime | None = None
) -> TelegramUser:
    if not raw:
        raise InitDataError("initData пуст")

    fields = dict(parse_qsl(raw, strict_parsing=False))
    signature = fields.pop("hash", None)
    if signature is None:
        raise InitDataError("в initData нет подписи")

    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    # compare_digest, а не ==: сравнение строк выходит из цикла на первом
    # различии, и по времени ответа подпись подбирается побайтово.
    # Сравниваются байты, а не строки: строковый вариант compare_digest падает
    # с TypeError на не-ASCII подписи, а её присылает кто угодно.
    if not hmac.compare_digest(expected.encode(), signature.encode()):
        raise InitDataError("подпись initData не совпала")

    try:
        auth_date = datetime.fromtimestamp(int(fields["auth_date"]), tz=UTC)
    except (KeyError, ValueError) as error:
        raise InitDataError("некорректный auth_date") from error

    if (now or datetime.now(UTC)) - auth_date > max_age:
        raise InitDataError("initData устарел")

    try:
        user = json.loads(fields["user"])
        return TelegramUser(
            telegram_id=int(user["id"]),
            username=user.get("username"),
            first_name=user.get("first_name"),
            language_code=user.get("language_code"),
        )
    except (KeyError, ValueError, TypeError) as error:
        raise InitDataError("в initData нет пользователя") from error
