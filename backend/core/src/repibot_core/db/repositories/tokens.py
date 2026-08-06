"""Доступ к одноразовым токенам."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import OneTimeToken, TokenType


class TokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        type: TokenType,  # имя поля модели, менять его дороже
        user_id: int,
        token_hash: str,
        expires_at: datetime,
        payload: dict[str, Any] | None = None,
    ) -> OneTimeToken:
        token = OneTimeToken(
            type=type,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            payload=payload,
        )
        self._session.add(token)
        await self._session.flush()
        return token

    async def find_usable(
        self, type: TokenType, token_hash: str, now: datetime
    ) -> OneTimeToken | None:
        statement = select(OneTimeToken).where(
            OneTimeToken.type == type,
            OneTimeToken.token_hash == token_hash,
            OneTimeToken.used_at.is_(None),
            OneTimeToken.expires_at > now,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def mark_used(self, token: OneTimeToken) -> None:
        token.used_at = datetime.now(UTC)
        await self._session.flush()

    async def invalidate_all(self, type: TokenType, user_id: int) -> None:
        """Гасит прежние токены того же типа.

        Запрошенный сброс пароля дважды не должен оставлять две рабочие ссылки:
        письмо могло уйти на адрес, к которому доступ уже потерян.
        """
        statement = (
            update(OneTimeToken)
            .where(
                OneTimeToken.type == type,
                OneTimeToken.user_id == user_id,
                OneTimeToken.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )
        await self._session.execute(statement)
