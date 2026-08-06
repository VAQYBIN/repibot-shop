"""Проверка initData. Подпись считается ровно так, как её ставит Telegram."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from repibot_core.security.initdata import InitDataError, parse_init_data

BOT_TOKEN = "123456:test-token"


def _sign(fields: dict[str, str], token: str = BOT_TOKEN) -> str:
    """Собирает initData так же, как Telegram: сортировка, перевод строки, HMAC."""
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def _fields(auth_date: datetime | None = None) -> dict[str, str]:
    moment = auth_date or datetime.now(UTC)
    user = '{"id":777,"first_name":"Иван","username":"ivan","language_code":"ru"}'
    return {"auth_date": str(int(moment.timestamp())), "user": user, "query_id": "AAA"}


def test_valid_init_data_is_parsed() -> None:
    parsed = parse_init_data(_sign(_fields()), bot_token=BOT_TOKEN, max_age=timedelta(days=1))

    assert parsed.telegram_id == 777
    assert parsed.username == "ivan"
    assert parsed.language_code == "ru"


def test_tampered_init_data_is_rejected() -> None:
    raw = _sign(_fields()).replace("777", "888")

    with pytest.raises(InitDataError):
        parse_init_data(raw, bot_token=BOT_TOKEN, max_age=timedelta(days=1))


def test_data_signed_with_another_token_is_rejected() -> None:
    raw = _sign(_fields(), token="999999:другой-токен")

    with pytest.raises(InitDataError):
        parse_init_data(raw, bot_token=BOT_TOKEN, max_age=timedelta(days=1))


def test_old_init_data_is_rejected() -> None:
    """Сутки — предел. Просроченный initData означает переигранный запрос."""
    raw = _sign(_fields(datetime.now(UTC) - timedelta(days=2)))

    with pytest.raises(InitDataError):
        parse_init_data(raw, bot_token=BOT_TOKEN, max_age=timedelta(days=1))


def test_init_data_without_hash_is_rejected() -> None:
    with pytest.raises(InitDataError):
        parse_init_data("auth_date=1&user=%7B%7D", bot_token=BOT_TOKEN, max_age=timedelta(days=1))


def test_empty_init_data_is_rejected() -> None:
    with pytest.raises(InitDataError):
        parse_init_data("", bot_token=BOT_TOKEN, max_age=timedelta(days=1))
