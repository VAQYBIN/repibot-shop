"""Вход по passkey.

Способ входа опознаёт человека и передаёт его AuthService — токены выдаёт
только он. Секрета на нашей стороне нет вовсе: в базе лежит публичный ключ,
и утечка базы не даёт войти ни в один аккаунт.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from repibot_core.db.models import User
from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import can_unlink
from repibot_core.security.webauthn import (
    RP_NAME,
    challenge_from_response,
    credential_id_from_response,
    relying_party,
)
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.services.challenges import ChallengeStore
from repibot_core.services.login_methods import login_methods
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

PURPOSE_REGISTER = "register"
PURPOSE_LOGIN = "login"

DEFAULT_KEY_NAME = "Ключ"
# Столько же, сколько в колонке: длинное имя обрезается, а не роняет вставку.
MAX_KEY_NAME_LENGTH = 64


@dataclass(frozen=True, slots=True)
class PasskeyView:
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None


class PasskeyAuth:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        auth: AuthService,
        challenges: ChallengeStore,
    ) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._challenges = challenges
        self._party = relying_party(settings.public_web_url)
        self._users = UserRepository(session)
        self._passkeys = PasskeyRepository(session)

    async def registration_options(self, user_id: int) -> dict[str, Any]:
        user = await self._require_user(user_id)
        # Уже зарегистрированные ключи перечисляются, чтобы аутентификатор не
        # завёл на этом же устройстве второй: человек получил бы два ключа,
        # неотличимых в списке.
        existing = await self._passkeys.list_for_user(user_id)
        options = generate_registration_options(
            rp_id=self._party.rp_id,
            rp_name=RP_NAME,
            # Идентификатор пользователя уходит в аутентификатор и возвращается
            # при входе как userHandle. Это внутренний номер, не почта: почту
            # человек меняет, а ключ должен пережить смену.
            user_id=str(user.id).encode(),
            user_name=self._display_name(user),
            user_display_name=user.name or self._display_name(user),
            authenticator_selection=AuthenticatorSelectionCriteria(
                # Discoverable: без этого на экране входа пришлось бы сначала
                # спрашивать почту, чтобы понять, чей ключ предлагать.
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            exclude_credentials=[
                PublicKeyCredentialDescriptor(id=row.credential_id) for row in existing
            ],
        )
        await self._challenges.remember(PURPOSE_REGISTER, options.challenge, user_id=user.id)
        return self._as_json(options_to_json(options))

    async def register(self, user_id: int, credential: dict[str, Any], name: str) -> None:
        challenge = self._challenge_of(credential)
        owner = await self._challenges.take(PURPOSE_REGISTER, challenge)
        if owner != str(user_id):
            raise AuthError("token_invalid", "challenge не выдавался этому пользователю")

        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=self._party.rp_id,
                expected_origin=self._party.origin,
            )
        except WebAuthnException as error:
            logger.warning("аутентификатор не принят при регистрации: %s", error)
            raise AuthError("invalid_credentials", "аутентификатор не принят") from error

        # Тот же ключ у другого аккаунта — это либо ошибка, либо попытка
        # привязать чужой аутентификатор. Уникальность держит и база, но
        # понятный код ответа она не вернёт.
        occupied = await self._passkeys.get_by_credential_id(verified.credential_id)
        if occupied is not None:
            raise AuthError("link_conflict", "этот ключ уже зарегистрирован")

        await self._passkeys.create(
            user_id=user_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports=self._transports(credential),
            name=(name.strip() or DEFAULT_KEY_NAME)[:MAX_KEY_NAME_LENGTH],
        )
        await self._session.commit()

    async def login_options(self) -> dict[str, Any]:
        """Параметры входа без указания пользователя: ключ сам скажет, чей он."""
        options = generate_authentication_options(
            rp_id=self._party.rp_id, user_verification=UserVerificationRequirement.PREFERRED
        )
        await self._challenges.remember(PURPOSE_LOGIN, options.challenge)
        return self._as_json(options_to_json(options))

    async def login(
        self, credential: dict[str, Any], *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        challenge = self._challenge_of(credential)
        if await self._challenges.take(PURPOSE_LOGIN, challenge) is None:
            raise AuthError("token_invalid", "challenge неизвестен или уже использован")

        try:
            credential_id = credential_id_from_response(credential)
        except ValueError as error:
            raise AuthError("token_invalid", str(error)) from error

        row = await self._passkeys.get_by_credential_id(credential_id)
        if row is None:
            raise AuthError("invalid_credentials", "ключ не зарегистрирован")

        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=self._party.rp_id,
                expected_origin=self._party.origin,
                credential_public_key=row.public_key,
                credential_current_sign_count=row.sign_count,
            )
        except WebAuthnException as error:
            # Отставший счётчик подписей означает клон ключа, а неверная
            # подпись — подделку. Наружу и в том, и в другом случае уходит
            # общий код: подробность помогает только подбирающему.
            logger.warning("ответ аутентификатора отклонён: %s", error)
            raise AuthError("invalid_credentials", "аутентификатор не принят") from error

        row.sign_count = verified.new_sign_count
        row.last_used_at = datetime.now(UTC)
        user = await self._users.get(row.user_id)
        if user is None:
            raise AuthError("invalid_credentials", "владелец ключа удалён")
        await self._session.commit()

        # Статус аккаунта и повышение роли проверяет AuthService: способ входа
        # их не дублирует, иначе правила разошлись бы между способами.
        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def list_keys(self, user_id: int) -> list[PasskeyView]:
        return [
            PasskeyView(
                id=row.id,
                name=row.name,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
            )
            for row in await self._passkeys.list_for_user(user_id)
        ]

    async def delete(self, user_id: int, passkey_id: int) -> None:
        row = await self._passkeys.get(passkey_id)
        # Чужой ключ не удаляется, и знать о его существовании тоже незачем:
        # ответ одинаков для несуществующего и для принадлежащего другому.
        if row is None or row.user_id != user_id:
            raise AuthError("not_found", "ключ не найден")

        user = await self._require_user(user_id)
        methods = await login_methods(self._session, user)
        if not can_unlink(methods, "passkey"):
            raise AuthError("last_login_method", "это единственный способ входа")

        await self._passkeys.delete(row)
        await self._session.commit()

    async def _require_user(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        return user

    def _challenge_of(self, credential: dict[str, Any]) -> bytes:
        try:
            return challenge_from_response(credential)
        except ValueError as error:
            raise AuthError("token_invalid", str(error)) from error

    @staticmethod
    def _as_json(options: str) -> dict[str, Any]:
        """Опции в том виде, в каком их ждёт `@simplewebauthn/browser`.

        Библиотека сама переводит поля в camelCase и байты в base64url —
        собирать словарь вручную значило бы повторять её правила кодирования.
        """
        parsed: dict[str, Any] = json.loads(options)
        return parsed

    @staticmethod
    def _transports(credential: dict[str, Any]) -> list[str] | None:
        response = credential.get("response")
        if not isinstance(response, dict):
            return None
        transports = response.get("transports")
        if not isinstance(transports, list):
            return None
        return [str(item) for item in transports]

    @staticmethod
    def _display_name(user: User) -> str:
        """Имя в системном окне выбора ключа: по нему человек узнаёт аккаунт."""
        if user.email is not None:
            return user.email
        if user.telegram_username is not None:
            return f"@{user.telegram_username}"
        return f"Re:Pibot #{user.id}"
