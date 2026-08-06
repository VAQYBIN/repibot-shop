"""Сколько способов входа осталось у пользователя."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.identity import can_unlink
from repibot_core.services.login_methods import login_methods

pytestmark = pytest.mark.docker


async def test_password_and_passkey_are_counted(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(
        email="user@example.org",
        password_hash="argon2",
        referral_code=await users.next_referral_code(),
    )
    await PasskeyRepository(db_session).create(
        user_id=user.id,
        credential_id=b"one",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()

    methods = await login_methods(db_session, user)

    assert methods.has_password is True
    assert methods.passkey_count == 1
    assert can_unlink(methods, "password") is True


async def test_single_passkey_cannot_be_removed(db_session: AsyncSession) -> None:
    """Единственный способ входа снять нельзя — иначе аккаунт запирается снаружи."""
    users = UserRepository(db_session)
    user = await users.create(referral_code=await users.next_referral_code())
    await PasskeyRepository(db_session).create(
        user_id=user.id,
        credential_id=b"only",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()

    methods = await login_methods(db_session, user)

    assert can_unlink(methods, "passkey") is False
