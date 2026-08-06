"""Доступ к passkey-ключам."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import PasskeyCredential


class PasskeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        credential_id: bytes,
        public_key: bytes,
        sign_count: int,
        transports: list[str] | None,
        name: str,
    ) -> PasskeyCredential:
        row = PasskeyCredential(
            user_id=user_id,
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            transports=transports,
            name=name,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, passkey_id: int) -> PasskeyCredential | None:
        return await self._session.get(PasskeyCredential, passkey_id)

    async def get_by_credential_id(self, credential_id: bytes) -> PasskeyCredential | None:
        statement = select(PasskeyCredential).where(
            PasskeyCredential.credential_id == credential_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_for_user(self, user_id: int) -> list[PasskeyCredential]:
        statement = (
            select(PasskeyCredential)
            .where(PasskeyCredential.user_id == user_id)
            .order_by(PasskeyCredential.created_at)
        )
        return list((await self._session.execute(statement)).scalars())

    async def count_for_user(self, user_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(PasskeyCredential)
            .where(PasskeyCredential.user_id == user_id)
        )
        return int((await self._session.execute(statement)).scalar_one())

    async def delete(self, row: PasskeyCredential) -> None:
        # Удаление через сессию, а не отдельным DELETE: иначе объект остаётся
        # в её карте идентичности, и следующий запрос по тому же ключу вернёт
        # запись, которой в базе уже нет.
        await self._session.delete(row)
        await self._session.flush()
