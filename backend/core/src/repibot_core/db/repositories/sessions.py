"""Доступ к сессиям."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> Session:
        item = Session(
            user_id=user_id,
            refresh_token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def get(self, session_id: UUID) -> Session | None:
        return await self._session.get(Session, session_id)

    async def find_by_token_hash(self, token_hash: str) -> Session | None:
        statement = select(Session).where(Session.refresh_token_hash == token_hash)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def find_by_previous_hash(self, token_hash: str) -> Session | None:
        statement = select(Session).where(Session.previous_token_hash == token_hash)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def rotate(self, item: Session, new_hash: str) -> None:
        item.previous_token_hash = item.refresh_token_hash
        item.refresh_token_hash = new_hash
        item.rotated_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke(self, item: Session) -> None:
        item.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_all(self, user_id: int, *, except_id: UUID | None = None) -> list[UUID]:
        """Отзывает сессии пользователя и возвращает идентификаторы отозванных.

        Идентификаторы нужны вызывающему: по ним access-токены помечаются
        недействительными в Valkey, иначе отзыв подействует только через
        время жизни access-токена.
        """
        statement = select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        revoked: list[UUID] = []
        for item in (await self._session.execute(statement)).scalars():
            if except_id is not None and item.id == except_id:
                continue
            item.revoked_at = datetime.now(UTC)
            revoked.append(item.id)
        await self._session.flush()
        return revoked

    async def list_active(self, user_id: int) -> list[Session]:
        statement = (
            select(Session)
            .where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.expires_at > datetime.now(UTC),
            )
            .order_by(Session.created_at.desc())
        )
        return list((await self._session.execute(statement)).scalars())
