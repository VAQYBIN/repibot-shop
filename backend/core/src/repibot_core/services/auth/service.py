"""Единственный путь выдачи сессии.

Любой способ входа заканчивается здесь: проверка статуса, повышение роли по
списку админов, запись в журнал и выдача токенов написаны один раз.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Session, User, UserRole, UserStatus
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.sessions import SessionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.tokens import (
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
)
from repibot_core.services.auth.types import AuthError, IssuedSession
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)

# Окно, внутри которого приход предыдущего refresh-токена считается гонкой
# вкладок, а не утечкой. Две вкладки, одновременно заметившие истёкший access,
# обновляются с разницей в миллисекунды; злоумышленник с украденной cookie
# приходит заметно позже.
ROTATION_RACE_WINDOW = timedelta(seconds=30)


class AuthService:
    def __init__(
        self, session: AsyncSession, settings: Settings, principals: PrincipalCache
    ) -> None:
        self._session = session
        self._settings = settings
        self._principals = principals
        self._sessions = SessionRepository(session)
        self._users = UserRepository(session)
        self._audit = AuditRepository(session)

    async def issue(
        self,
        user: User,
        *,
        user_agent: str | None,
        ip: str | None,
        with_refresh: bool,
    ) -> IssuedSession:
        if user.status is not UserStatus.active:
            raise AuthError("forbidden", "аккаунт заблокирован")

        await self._promote_if_admin(user, ip=ip)

        raw_refresh = generate_opaque_token() if with_refresh else None
        # Сессия создаётся всегда, даже без refresh: её идентификатор попадает
        # в access-токен, и без него нельзя ни отозвать доступ, ни показать
        # список устройств.
        expires_at = datetime.now(UTC) + timedelta(days=self._settings.refresh_token_ttl_days)
        row = await self._sessions.create(
            user_id=user.id,
            # У сессии без refresh (MiniApp) поле всё равно заполняется: оно
            # NOT NULL и уникально. Значение — хеш от выброшенного случайного
            # токена: предъявить его нельзя, прообраза не знает никто, и в базе
            # оно выглядит хешем, а не испорченной строкой.
            token_hash=hash_opaque_token(raw_refresh or generate_opaque_token()),
            expires_at=expires_at,
            user_agent=(user_agent or None) and user_agent[:256],
            ip=ip,
        )
        await self._session.commit()

        return self._pack(
            user.id,
            row.id,
            raw_refresh,
            expires_at if raw_refresh else None,
            is_admin=user.role is UserRole.admin,
        )

    async def refresh(
        self, raw_token: str, *, user_agent: str | None, ip: str | None
    ) -> IssuedSession:
        token_hash = hash_opaque_token(raw_token)
        row = await self._sessions.find_by_token_hash(token_hash)

        if row is None:
            # Токена нет среди текущих. Возможно, это предыдущий — тогда решает
            # окно ротации: гонка вкладок обслуживается, утечка отзывается.
            row = await self._handle_possible_reuse(token_hash)
            if row is None:
                raise AuthError("token_invalid", "токен не найден")

        now = datetime.now(UTC)
        if row.revoked_at is not None or row.expires_at <= now:
            raise AuthError("token_invalid", "сессия недействительна")

        user = await self._users.get(row.user_id)
        if user is None:
            raise AuthError("token_invalid", "пользователь удалён")
        if user.status is not UserStatus.active:
            raise AuthError("forbidden", "аккаунт заблокирован")

        new_raw = generate_opaque_token()
        await self._sessions.rotate(row, hash_opaque_token(new_raw))
        if user_agent:
            row.user_agent = user_agent[:256]
        if ip:
            row.ip = ip
        await self._session.commit()

        return self._pack(
            row.user_id,
            row.id,
            new_raw,
            row.expires_at,
            is_admin=user.role is UserRole.admin,
        )

    async def logout(self, session_id: UUID) -> None:
        row = await self._sessions.get(session_id)
        if row is None or row.revoked_at is not None:
            return
        await self._sessions.revoke(row)
        await self._principals.mark_session_revoked(
            session_id, ttl_seconds=self._settings.access_token_ttl_minutes * 60
        )
        await self._session.commit()

    async def revoke_session(self, user_id: int, session_id: UUID) -> None:
        row = await self._sessions.get(session_id)
        # Чужую сессию отозвать нельзя, и знать о её существовании тоже:
        # ответ одинаков для несуществующей и для принадлежащей другому.
        if row is None or row.user_id != user_id:
            raise AuthError("not_found", "сессия не найдена")
        await self.logout(session_id)

    async def revoke_other_sessions(self, user_id: int, current_id: UUID) -> None:
        revoked = await self._sessions.revoke_all(user_id, except_id=current_id)
        for session_id in revoked:
            await self._principals.mark_session_revoked(
                session_id, ttl_seconds=self._settings.access_token_ttl_minutes * 60
            )
        await self._session.commit()

    async def revoke_all_sessions(self, user_id: int) -> None:
        """Отзывает всё. Используется при смене и сбросе пароля."""
        revoked = await self._sessions.revoke_all(user_id)
        for session_id in revoked:
            await self._principals.mark_session_revoked(
                session_id, ttl_seconds=self._settings.access_token_ttl_minutes * 60
            )
        await self._session.commit()

    async def _handle_possible_reuse(self, token_hash: str) -> Session | None:
        """Разбирает приход предыдущего токена.

        Возвращает сессию, если это гонка вкладок внутри окна — тогда вызывающий
        просто выдаёт новую пару. Возвращает None, если это утечка: сессия
        отзывается целиком, потому что копию токена держит кто-то ещё, и какой
        из двух держателей настоящий, мы не знаем.
        """
        row = await self._sessions.find_by_previous_hash(token_hash)
        if row is None or row.revoked_at is not None:
            return None

        rotated_at = row.rotated_at or row.created_at
        if datetime.now(UTC) - rotated_at <= ROTATION_RACE_WINDOW:
            return row

        await self._sessions.revoke(row)
        await self._principals.mark_session_revoked(
            row.id, ttl_seconds=self._settings.access_token_ttl_minutes * 60
        )
        await self._audit.record(
            "session.reuse_detected", "session", actor_id=row.user_id, entity_id=str(row.id)
        )
        await self._session.commit()
        logger.warning("повторное использование refresh-токена", extra={"session_id": str(row.id)})
        return None

    async def _promote_if_admin(self, user: User, *, ip: str | None) -> None:
        if user.telegram_id is None or user.role is UserRole.admin:
            return
        if user.telegram_id not in self._settings.admin_telegram_ids:
            return

        before = user.role.value
        user.role = UserRole.admin
        await self._audit.record(
            "role.granted",
            "user",
            actor_id=user.id,
            entity_id=str(user.id),
            before={"role": before},
            after={"role": UserRole.admin.value},
            ip=ip,
        )
        await self._principals.invalidate(user.id)
        logger.info("роль admin выдана по списку ADMIN_TELEGRAM_IDS", extra={"user_id": user.id})

    def _pack(
        self,
        user_id: int,
        session_id: UUID,
        raw_refresh: str | None,
        refresh_expires_at: datetime | None,
        *,
        is_admin: bool,
    ) -> IssuedSession:
        ttl = self._settings.access_token_ttl_minutes
        return IssuedSession(
            access_token=create_access_token(
                user_id,
                session_id,
                secret=self._settings.jwt_secret.get_secret_value(),
                ttl_minutes=ttl,
            ),
            refresh_token=raw_refresh,
            session_id=session_id,
            access_expires_in=ttl * 60,
            refresh_expires_at=refresh_expires_at,
            is_admin=is_admin,
        )
