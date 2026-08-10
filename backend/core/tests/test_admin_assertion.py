"""Короткие подписанные утверждения только для гейта админских страниц."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

from repibot_core.security.admin_assertion import create_admin_assertion

SECRET = "0123456789abcdef0123456789abcdef"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def test_admin_assertion_is_an_hmac_signed_expiring_admin_claim() -> None:
    """Правка роли, срока или байтов payload обязана ломать подпись."""
    expires_at = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)

    assertion = create_admin_assertion(SECRET, expires_at=expires_at)

    encoded_claims, signature = assertion.split(".")
    expected_signature = _base64url(
        hmac.new(SECRET.encode("utf-8"), encoded_claims.encode("ascii"), hashlib.sha256).digest()
    )
    assert hmac.compare_digest(signature, expected_signature)
    assert json.loads(base64.urlsafe_b64decode(encoded_claims + "==")) == {
        "exp": int(expires_at.timestamp()),
        "role": "admin",
        "v": 1,
    }
