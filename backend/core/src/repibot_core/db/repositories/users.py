"""Доступ к пользователям."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.domain.identity import generate_referral_code, normalize_email


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == normalize_email(email))
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        statement = select(User).where(User.telegram_id == telegram_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(self, **fields: Any) -> User:
        if "email" in fields and fields["email"] is not None:
            fields["email"] = normalize_email(fields["email"])
        user = User(**fields)
        self._session.add(user)
        await self._session.flush()
        return user

    async def next_referral_code(self) -> str:
        """Подбирает свободный код.

        Уникальность держит ограничение в базе; здесь просто уменьшается
        вероятность нарваться на него. Пять попыток при алфавите из 31 символа
        и восьми знаках — с запасом.
        """
        for _ in range(5):
            code = generate_referral_code()
            statement = select(User.id).where(User.referral_code == code)
            if (await self._session.execute(statement)).first() is None:
                return code
        msg = "не удалось подобрать свободный реферальный код"
        raise RuntimeError(msg)
