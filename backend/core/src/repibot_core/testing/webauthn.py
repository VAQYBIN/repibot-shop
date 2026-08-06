"""Программный аутентификатор для тестов passkey.

Собирает ответы ровно того вида, что присылает браузер: clientDataJSON,
authenticatorData и подпись ES256. Настоящего аутентификатора в CI нет, а
записанные чужие ответы привязаны к чужим challenge и origin — проверить ими
можно только то, что библиотека умеет разбирать саму себя.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url, encode_cbor

# Нулевой AAGUID означает «модель устройства не раскрывается» — так делают
# платформенные аутентификаторы, и attestation с fmt=none его не проверяет.
AAGUID = b"\x00" * 16

FLAG_USER_PRESENT = 0x01
FLAG_USER_VERIFIED = 0x04
FLAG_ATTESTED_DATA = 0x40


class SoftAuthenticator:
    def __init__(self, *, rp_id: str, origin: str, credential_id: bytes | None = None) -> None:
        self.rp_id = rp_id
        self.origin = origin
        self.credential_id = credential_id or secrets.token_bytes(32)
        self.sign_count = 0
        self._key = ec.generate_private_key(ec.SECP256R1())

    def register(self, challenge: bytes) -> dict[str, Any]:
        client_data = self._client_data("webauthn.create", challenge)
        auth_data = self._auth_data(
            FLAG_USER_PRESENT | FLAG_USER_VERIFIED | FLAG_ATTESTED_DATA, attested=True
        )
        attestation = encode_cbor({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "type": "public-key",
            "clientExtensionResults": {},
        }

    def authenticate(self, challenge: bytes, *, user_handle: bytes) -> dict[str, Any]:
        self.sign_count += 1
        client_data = self._client_data("webauthn.get", challenge)
        auth_data = self._auth_data(FLAG_USER_PRESENT | FLAG_USER_VERIFIED, attested=False)
        signature = self._key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(user_handle),
            },
            "type": "public-key",
            "clientExtensionResults": {},
        }

    def _cose_key(self) -> bytes:
        """Публичный ключ в формате COSE_Key: kty EC2, alg ES256, кривая P-256."""
        numbers = self._key.public_key().public_numbers()
        return encode_cbor(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )

    def _client_data(self, kind: str, challenge: bytes) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": bytes_to_base64url(challenge),
                "origin": self.origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode()

    def _auth_data(self, flags: int, *, attested: bool) -> bytes:
        data = hashlib.sha256(self.rp_id.encode()).digest()
        data += bytes([flags])
        data += self.sign_count.to_bytes(4, "big")
        if attested:
            key = self._cose_key()
            data += AAGUID + len(self.credential_id).to_bytes(2, "big") + self.credential_id + key
        return data
