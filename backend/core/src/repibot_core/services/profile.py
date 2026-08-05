"""Профиль: то, что пользователь меняет о себе сам."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import UserRole
from repibot_core.db.repositories.sessions import SessionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import PasswordPolicyError, normalize_email, validate_password
from repibot_core.security.passwords import hash_password, verify_password
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import Settings


@dataclass(frozen=True, slots=True)
class ProfileView:
    user_id: int
    email: str | None
    email_verified: bool
    telegram_username: str | None
    name: str | None
    language: str
    role: UserRole
    referral_code: str
    has_password: bool
    has_telegram: bool
    passkey_count: int


@dataclass(frozen=True, slots=True)
class SessionView:
    session_id: UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    is_current: bool


class ProfileService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        auth: AuthService,
        principals: PrincipalCache,
        letters: PasswordAuth,
    ) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._principals = principals
        self._letters = letters
        self._users = UserRepository(session)
        self._sessions = SessionRepository(session)

    async def view(self, user_id: int) -> ProfileView:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        return ProfileView(
            user_id=user.id,
            email=user.email,
            email_verified=user.email_verified_at is not None,
            telegram_username=user.telegram_username,
            name=user.name,
            language=user.language,
            role=user.role,
            referral_code=user.referral_code,
            has_password=user.password_hash is not None,
            has_telegram=user.telegram_id is not None,
            # Passkey появятся в плане 1b; до тех пор их ноль, и это честное
            # значение, а не заглушка: таблицы ещё нет.
            passkey_count=0,
        )

    async def update(self, user_id: int, *, name: str | None, language: str) -> ProfileView:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")
        if language not in self._settings.supported_languages:
            raise AuthError("validation_error", "язык не поддерживается")

        user.name = name
        user.language = language
        await self._session.commit()
        # Язык лежит в кэше вместе с ролью: без сброса бот ответит на прежнем.
        await self._principals.invalidate(user_id)
        return await self.view(user_id)

    async def set_password(self, user_id: int, *, current: str | None, new: str) -> None:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")

        # Пароля может не быть вовсе — у вошедшего через Telegram. Тогда это
        # установка первого пароля, и текущий спрашивать не с чего.
        if user.password_hash is not None and not verify_password(
            user.password_hash, current or ""
        ):
            raise AuthError("invalid_credentials", "текущий пароль неверен")

        try:
            validate_password(new, email=user.email)
        except PasswordPolicyError as error:
            raise AuthError("weak_password", str(error)) from error

        user.password_hash = hash_password(new)
        await self._session.commit()

    async def request_email_change(self, user_id: int, new_email: str) -> None:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("not_found", "пользователь не найден")

        address = normalize_email(new_email)
        occupied = await self._users.get_by_email(address)
        if occupied is not None and occupied.id != user_id:
            raise AuthError("email_taken", "адрес уже занят")

        # Письмо уходит на новый адрес, а сам адрес пока не меняется: пока
        # владение им не доказано, менять способ входа нельзя.
        await self._letters.issue_email_change(user, address)

    async def confirm_email_change(self, raw_token: str) -> None:
        await self._letters.apply_email_change(raw_token)

    async def list_sessions(self, user_id: int, current_id: UUID) -> list[SessionView]:
        return [
            SessionView(
                session_id=item.id,
                user_agent=item.user_agent,
                ip=item.ip,
                created_at=item.created_at,
                is_current=item.id == current_id,
            )
            for item in await self._sessions.list_active(user_id)
        ]
