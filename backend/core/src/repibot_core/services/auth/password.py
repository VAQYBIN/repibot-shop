"""Вход паролем: регистрация, подтверждение адреса, вход, сброс.

Способ входа опознаёт человека и передаёт его AuthService — токены выдаёт
только он. Здесь же живут письма: у них тот же жизненный цикл, что у пароля.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TokenType, User
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.tokens import TokenRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import (
    TOKEN_LIFETIMES,
    PasswordPolicyError,
    normalize_email,
    validate_password,
)
from repibot_core.security.passwords import DUMMY_HASH, hash_password, verify_password
from repibot_core.security.tokens import generate_opaque_token, hash_opaque_token
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.services.email_dispatch import (
    TOPIC_EMAIL_CHANGE,
    TOPIC_EMAIL_VERIFY,
    TOPIC_PASSWORD_RESET,
)
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

_LINK_PATHS = {
    TokenType.email_verify: "/verify-email",
    TokenType.password_reset: "/reset-password",
    TokenType.email_change: "/account/confirm-email",
}
_TOPICS = {
    TokenType.email_verify: TOPIC_EMAIL_VERIFY,
    TokenType.password_reset: TOPIC_PASSWORD_RESET,
    TokenType.email_change: TOPIC_EMAIL_CHANGE,
}


class PasswordAuth:
    def __init__(self, session: AsyncSession, settings: Settings, auth: AuthService) -> None:
        self._session = session
        self._settings = settings
        self._auth = auth
        self._users = UserRepository(session)
        self._tokens = TokenRepository(session)
        self._outbox = OutboxRepository(session)

    async def register(self, *, email: str, password: str, language: str) -> None:
        address = normalize_email(email)
        try:
            validate_password(password, email=address)
        except PasswordPolicyError as error:
            raise AuthError("weak_password", str(error)) from error

        existing = await self._users.get_by_email(address)
        if existing is not None and existing.email_verified_at is not None:
            raise AuthError("email_taken", "адрес уже занят")

        if existing is not None:
            # Аккаунт есть, но адрес не подтверждён: значит войти им никто не
            # может. Перезаписываем пароль и язык и отправляем письмо заново —
            # иначе брошенная регистрация занимает адрес навсегда.
            existing.password_hash = hash_password(password)
            existing.language = language
            user = existing
        else:
            user = await self._users.create(
                email=address,
                password_hash=hash_password(password),
                language=language,
                referral_code=await self._users.next_referral_code(),
            )

        await self._issue_letter(user, TokenType.email_verify)
        await self._commit_and_notify()

    async def resend_verification(self, email: str) -> None:
        """Повторное письмо. Ответ вызывающему одинаков в любом случае."""
        user = await self._users.get_by_email(email)
        if user is None or user.email_verified_at is not None:
            return
        await self._issue_letter(user, TokenType.email_verify)
        await self._commit_and_notify()

    async def verify_email(
        self, raw_token: str, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        token = await self._consume(TokenType.email_verify, raw_token)
        user = await self._require_user(token.user_id)

        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(UTC)
        await self._session.commit()

        # Сессия выдаётся сразу: человек уже подтвердил владение адресом,
        # заставлять его вводить пароль на следующем экране незачем.
        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def login(
        self, *, email: str, password: str, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        user = await self._users.get_by_email(email)
        # Хеш сверяется даже для неизвестного адреса: без этого время ответа
        # сообщает, зарегистрирован ли он.
        stored = user.password_hash if user is not None else DUMMY_HASH
        matches = verify_password(stored, password)

        if user is None or not matches:
            raise AuthError("invalid_credentials", "неверный адрес или пароль")
        if user.email_verified_at is None:
            raise AuthError("email_not_verified", "адрес не подтверждён")

        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def request_reset(self, email: str) -> None:
        user = await self._users.get_by_email(email)
        if user is None or user.email is None:
            logger.info("сброс пароля запрошен для неизвестного адреса")
            return
        await self._issue_letter(user, TokenType.password_reset)
        await self._commit_and_notify()

    async def reset(
        self, raw_token: str, new_password: str, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        token = await self._consume(TokenType.password_reset, raw_token)
        user = await self._require_user(token.user_id)

        try:
            validate_password(new_password, email=user.email)
        except PasswordPolicyError as error:
            raise AuthError("weak_password", str(error)) from error

        user.password_hash = hash_password(new_password)
        # Сброс пароля — это либо забытый пароль, либо угон. В обоих случаях
        # прежние сессии должны прекратиться.
        await self._session.commit()
        await self._auth.revoke_all_sessions(user.id)

        return await self._auth.issue(user, user_agent=user_agent, ip=ip, with_refresh=True)

    async def _issue_letter(
        self, user: User, kind: TokenType, *, payload: dict[str, Any] | None = None
    ) -> None:
        """Создаёт одноразовый токен и ставит письмо в очередь.

        Прежние токены того же типа гасятся: две рабочие ссылки на сброс
        пароля — это две возможности им воспользоваться.
        """
        await self._tokens.invalidate_all(kind, user.id)

        raw = generate_opaque_token()
        await self._tokens.create(
            type=kind,
            user_id=user.id,
            token_hash=hash_opaque_token(raw),
            expires_at=datetime.now(UTC) + TOKEN_LIFETIMES[kind],
            payload=payload,
        )

        recipient = payload.get("email") if payload else user.email
        if recipient is None:
            msg = "письмо некуда отправить"
            raise AuthError("token_invalid", msg)

        await self._outbox.add(
            _TOPICS[kind],
            {
                "to": recipient,
                "language": user.language,
                "link": f"{self._settings.public_web_url}{_LINK_PATHS[kind]}?token={raw}",
            },
        )

    async def _consume(self, kind: TokenType, raw_token: str) -> Any:
        token = await self._tokens.find_usable(
            kind, hash_opaque_token(raw_token), datetime.now(UTC)
        )
        if token is None:
            raise AuthError("token_invalid", "ссылка недействительна или уже использована")
        await self._tokens.mark_used(token)
        return token

    async def _require_user(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise AuthError("token_invalid", "пользователь не найден")
        return user

    async def _commit_and_notify(self) -> None:
        """Фиксирует транзакцию и просит воркер разобрать очередь сейчас.

        Постановка задачи идёт после коммита: до него письма в базе ещё нет,
        и воркер, успевший начать работу, ничего бы не нашёл. Отказ брокера не
        отменяет регистрацию — очередь всё равно разберётся по расписанию.
        """
        await self._session.commit()

        from repibot_core.tasks import process_outbox

        try:
            await process_outbox.kiq()
        except Exception:  # недоступный брокер не должен ломать регистрацию
            logger.warning("не удалось поставить задачу разбора outbox", exc_info=True)
