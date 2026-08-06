"""Какими способами человек может войти прямо сейчас.

Профилю это нужно для показа, отвязке — для проверки «останется ли чем войти».
Считается в одном месте: разойтись двум подсчётам ничего не мешает, а цена
расхождения — запертый снаружи аккаунт.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.domain.identity import LoginMethods


async def login_methods(session: AsyncSession, user: User) -> LoginMethods:
    return LoginMethods(
        has_password=user.password_hash is not None,
        has_telegram=user.telegram_id is not None,
        passkey_count=await PasskeyRepository(session).count_for_user(user.id),
    )
