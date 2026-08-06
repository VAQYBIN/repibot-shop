"""PKCE: доказательство того, что код обменивает тот же клиент, что его просил.

Без него перехваченный код обменивается кем угодно, знающим client_secret, —
а секрет живёт на сервере, но код проходит через браузер и историю переходов.
"""

from __future__ import annotations

import base64
import hashlib
import secrets

# 64 случайных байта дают 86 символов base64url — внутри разрешённых RFC 7636
# сорока трёх и ста двадцати восьми.
VERIFIER_BYTES = 64


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(VERIFIER_BYTES)


def code_challenge(verifier: str) -> str:
    """S256, а не plain: plain отправляет verifier в адресной строке."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
