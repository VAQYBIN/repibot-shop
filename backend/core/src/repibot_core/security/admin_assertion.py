"""Короткое подписанное утверждение для гейта админских страниц в Next.

Пропуском в API оно намеренно не является: изменения на бэкенде
по-прежнему проверяют роль по access-токену. Эта cookie нужна лишь
затем, чтобы Next отбросил запрос страницы до того, как отрисует
чувствительную разметку.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime

ADMIN_ASSERTION_VERSION = 1


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def create_admin_assertion(secret: str, *, expires_at: datetime) -> str:
    """Подписывает ровно то утверждение, которое проверяет прокси Next.

    Формат `base64url(JSON).base64url(HMAC)` избавляет веб-сборку от
    зависимости на JWT и остаётся привычным однозначным HMAC-SHA256.
    """
    claims = {
        "exp": int(expires_at.timestamp()),
        "role": "admin",
        "v": ADMIN_ASSERTION_VERSION,
    }
    encoded_claims = _base64url(
        json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        secret.encode("utf-8"), encoded_claims.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{encoded_claims}.{_base64url(signature)}"
