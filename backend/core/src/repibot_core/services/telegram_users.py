"""Пользователь, пришедший в бот.

Отдельно от services/auth/telegram.py: там вход с выдачей токенов, здесь —
обслуживание диалога в боте, где токены не нужны вовсе.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.users import UserRepository
from repibot_core.settings import Settings


class TelegramUserService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)

    async def ensure(
        self,
        telegram_id: int,
        *,
        username: str | None,
        first_name: str | None,
        language_code: str | None,
    ) -> User:
        """Находит или создаёт пользователя.

        Написавший боту — уже пользователь: без записи в базе ему нельзя ни
        выбрать язык, ни получить уведомление.
        """
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is not None:
            user.telegram_username = username
            if user.name is None:
                user.name = first_name
            await self._session.commit()
            return user

        user = await self._users.create(
            telegram_id=telegram_id,
            telegram_username=username,
            name=first_name,
            language=self._language(language_code),
            referral_code=await self._users.next_referral_code(),
        )
        await self._session.commit()
        return user

    async def set_language(self, telegram_id: int, language: str) -> None:
        user = await self._users.get_by_telegram_id(telegram_id)
        if user is None:
            return
        user.language = language
        await self._session.commit()

    def _language(self, code: str | None) -> str:
        if code is None:
            return self._settings.default_language
        short = code.split("-")[0]
        return (
            short
            if short in self._settings.supported_languages
            else self._settings.default_language
        )
