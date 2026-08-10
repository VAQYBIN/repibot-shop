"""A short-lived signed claim for Next's admin-route presentation gate.

The assertion is deliberately not an API credential.  Backend mutations keep
using the access-token role dependency; this cookie only lets Next discard an
admin-page request before it can render sensitive markup.
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
    """Signs the exact compact claim which the Next proxy verifies.

    Keeping this as `base64url(JSON).base64url(HMAC)` avoids placing a JWT
    dependency in the web bundle while retaining a conventional, unambiguous
    HMAC-SHA256 wire format.
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
