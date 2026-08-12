"""Блокировка аккаунта и заглушение поддержки.

Отдельный сервис, потому что зовут его из разных мест: команда в рабочем
чате сегодня, экран админки завтра. Журнал ведётся здесь же — решение о
блокировке обязано оставлять след независимо от того, кто его принял.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User, UserRole, UserStatus
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.errors import ServiceError

STAFF_ROLES = frozenset({UserRole.support, UserRole.admin})


class ModerationService:
    """Транзакцию закрывает вызывающий."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._audit = AuditRepository(session)

    async def ban(self, user_id: int, *, actor_id: int | None) -> bool:
        """Закрывает аккаунт целиком: и покупки, и разговор."""
        user = await self._require(user_id)
        if user.role in STAFF_ROLES:
            # Иначе рабочий чат становится оружием против собственных коллег:
            # прав на это внутри супергруппы никто не разграничивает.
            msg = "нельзя заблокировать сотрудника"
            raise ServiceError(msg, "staff_immune")
        if user.status is UserStatus.banned:
            return False
        user.status = UserStatus.banned
        await self._record("user.ban", user, before="active", after="banned", actor_id=actor_id)
        return True

    async def unban(self, user_id: int, *, actor_id: int | None) -> bool:
        """Возвращает аккаунт в работу."""
        user = await self._require(user_id)
        if user.status is not UserStatus.banned:
            return False
        user.status = UserStatus.active
        await self._record("user.unban", user, before="banned", after="active", actor_id=actor_id)
        return True

    async def mute_support(self, user_id: int, *, actor_id: int | None) -> bool:
        """Закрывает разговор, оставляя подписку, кабинет и оплату нетронутыми."""
        user = await self._require(user_id)
        if user.support_muted_at is not None:
            # Повтор не обновляет момент: он отвечает на вопрос «когда закрыли»,
            # и вторая команда стёрла бы настоящий ответ.
            return False
        user.support_muted_at = datetime.now(UTC)
        await self._record(
            "user.support_mute", user, before="open", after="muted", actor_id=actor_id
        )
        return True

    async def unmute_support(self, user_id: int, *, actor_id: int | None) -> bool:
        """Снова открывает разговор."""
        user = await self._require(user_id)
        if user.support_muted_at is None:
            return False
        user.support_muted_at = None
        await self._record(
            "user.support_unmute", user, before="muted", after="open", actor_id=actor_id
        )
        return True

    async def _require(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            # Тема поддержки живёт дольше аккаунта: команда по удалённому
            # человеку обязана стать отказом, а не падением обработчика.
            msg = "пользователь не найден"
            raise ServiceError(msg, "not_found")
        return user

    async def _record(
        self, action: str, user: User, *, before: str, after: str, actor_id: int | None
    ) -> None:
        """Состояние пишется словом, а не снимком строки: спор разбирают глазами."""
        await self._audit.record(
            action,
            "user",
            actor_id=actor_id,
            entity_id=str(user.id),
            before={"state": before},
            after={"state": after},
        )
