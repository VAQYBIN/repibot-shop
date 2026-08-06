"""Вход через Telegram по OpenID Connect.

Адреса взяты из discovery-документа `oauth.telegram.org` и зафиксированы
константами: один сетевой запрос на каждый вход и без того нужен, а
рассинхронизация с discovery проявилась бы отказом на первом же шаге.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from redis.asyncio import Redis

from repibot_core.services.auth.types import AuthError
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

ISSUER = "https://oauth.telegram.org"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/auth"
TOKEN_ENDPOINT = f"{ISSUER}/token"
JWKS_URI = f"{ISSUER}/.well-known/jwks.json"

# telegram:bot_access даёт боту право написать первым: без него
# зарегистрировавшийся на сайте не получил бы ни одного уведомления.
# phone не запрашивается — телефон не нужен, а хранить его значит отвечать за
# него.
SCOPES = "openid profile telegram:bot_access"

# Список закрыт намеренно: принимать алгоритм из заголовка токена — известный
# способ подсунуть «none» или подпись симметричным ключом.
ALGORITHMS = ("RS256", "ES256", "EdDSA", "ES256K")

JWKS_CACHE_KEY = "telegram:oidc:jwks"
JWKS_CACHE_TTL_SECONDS = 3600
TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class OidcIdentity:
    """Кто пришёл. Единственный источник — ID-токен: userinfo у Telegram нет."""

    telegram_id: int
    username: str | None
    name: str | None


class TelegramOidc:
    def __init__(
        self, settings: Settings, redis: Redis, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    @property
    def is_configured(self) -> bool:
        """Без Client ID кнопку входа показывать нечему: BotFather её не выдал."""
        return bool(self._settings.telegram_oidc_client_id)

    def authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        query = urlencode(
            {
                "client_id": self._settings.telegram_oidc_client_id,
                "response_type": "code",
                "scope": SCOPES,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{AUTHORIZATION_ENDPOINT}?{query}"

    async def exchange(self, *, code: str, code_verifier: str, redirect_uri: str) -> str:
        """Меняет код на ID-токен. Секрет уходит в теле, а не в адресе."""
        secret = self._settings.telegram_oidc_client_secret.get_secret_value()
        try:
            response = await self._client.post(
                TOKEN_ENDPOINT,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                    "client_id": self._settings.telegram_oidc_client_id,
                    "client_secret": secret,
                },
            )
        except httpx.HTTPError as error:
            logger.warning("обмен кода Telegram не удался: %s", type(error).__name__)
            raise AuthError("invalid_credentials", "Telegram недоступен") from error

        if response.status_code != httpx.codes.OK:
            # Тело ответа в журнал не идёт: в нём эхом возвращается код.
            logger.warning("Telegram отказал в обмене кода: %s", response.status_code)
            raise AuthError("invalid_credentials", "код не принят")

        token = response.json().get("id_token")
        if not isinstance(token, str) or not token:
            raise AuthError("invalid_credentials", "ответ Telegram без ID-токена")
        return token

    async def verify_id_token(self, token: str) -> OidcIdentity:
        key = await self._signing_key(token)
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(ALGORITHMS),
                audience=self._settings.telegram_oidc_client_id,
                issuer=ISSUER,
            )
        except jwt.PyJWTError as error:
            logger.warning("ID-токен Telegram отклонён: %s", type(error).__name__)
            raise AuthError("invalid_credentials", "ID-токен не принят") from error

        try:
            telegram_id = int(claims["sub"])
        except (KeyError, TypeError, ValueError) as error:
            raise AuthError("invalid_credentials", "в ID-токене нет sub") from error

        return OidcIdentity(
            telegram_id=telegram_id,
            username=claims.get("preferred_username"),
            name=claims.get("name"),
        )

    async def _signing_key(self, token: str) -> Any:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as error:
            raise AuthError("invalid_credentials", "заголовок ID-токена не разбирается") from error

        key = self._find_key(await self._jwks(), kid)
        if key is None:
            # Ключи ротируются: незнакомый kid — повод перечитать JWKS, а не
            # отказать. Второй промах уже означает чужую подпись.
            key = self._find_key(await self._jwks(force=True), kid)
        if key is None:
            raise AuthError("invalid_credentials", "ключ подписи неизвестен")
        return key

    @staticmethod
    def _find_key(jwks: dict[str, Any], kid: str | None) -> Any:
        for entry in jwks.get("keys", []):
            if kid is not None and entry.get("kid") != kid:
                continue
            try:
                return jwt.PyJWK.from_dict(entry).key
            except jwt.PyJWKError as error:
                # Набор ключей общий на все алгоритмы Telegram: запись, которую
                # PyJWT собрать не может, пропускается, а не валит проверку.
                logger.warning("ключ из JWKS Telegram не разобран: %s", error)
        return None

    async def _jwks(self, *, force: bool = False) -> dict[str, Any]:
        if not force:
            cached = await self._redis.get(JWKS_CACHE_KEY)
            if cached is not None:
                return dict(json.loads(cached))

        try:
            response = await self._client.get(JWKS_URI)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise AuthError("invalid_credentials", "JWKS Telegram недоступен") from error

        await self._redis.set(JWKS_CACHE_KEY, response.text, ex=JWKS_CACHE_TTL_SECONDS)
        return dict(response.json())
