"""Сборка initData для тестов и локальной отладки.

Лежит в пакете, а не в тестах: тем же способом MiniApp проверяется руками, и
дублировать подпись в каждом наборе тестов не нужно.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlencode


def build_init_data(
    *,
    bot_token: str,
    telegram_id: int = 777,
    username: str | None = "ivan",
    first_name: str = "Иван",
    language_code: str = "ru",
    auth_date: datetime | None = None,
) -> str:
    user = json.dumps(
        {
            "id": telegram_id,
            "first_name": first_name,
            "username": username,
            "language_code": language_code,
        },
        ensure_ascii=False,
    )
    fields = {
        "auth_date": str(int((auth_date or datetime.now(UTC)).timestamp())),
        "user": user,
        "query_id": "AAA",
    }
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})
