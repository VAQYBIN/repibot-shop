"""Доступ к выданным триалам."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TrialGrant


class TrialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, telegram_id: int) -> TrialGrant | None:
        return await self._session.get(TrialGrant, telegram_id)

    async def create(self, *, telegram_id: int, user_id: int | None) -> TrialGrant:
        """Отметка «этому Telegram триал уже выдавали».

        Запись переживает удаление аккаунта — `user_id` при нём обнуляется,
        а строка остаётся, — поэтому повторный триал через новую регистрацию
        не получить.
        """
        grant = TrialGrant(telegram_id=telegram_id, user_id=user_id)
        self._session.add(grant)
        await self._session.flush()
        return grant
