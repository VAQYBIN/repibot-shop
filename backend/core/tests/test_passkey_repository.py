"""Хранение passkey-ключей."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.db.repositories.passkeys import PasskeyRepository
from repibot_core.db.repositories.users import UserRepository

pytestmark = pytest.mark.docker


async def _user(session: AsyncSession, email: str = "user@example.org") -> User:
    users = UserRepository(session)
    user = await users.create(email=email, referral_code=await users.next_referral_code())
    await session.commit()
    return user


async def test_credential_is_found_by_its_raw_identifier(db_session: AsyncSession) -> None:
    """Вход по passkey начинается с идентификатора ключа: пользователь неизвестен."""
    user = await _user(db_session)
    passkeys = PasskeyRepository(db_session)
    await passkeys.create(
        user_id=user.id,
        credential_id=b"credential-one",
        public_key=b"public-key",
        sign_count=0,
        transports=["internal"],
        name="Ноутбук",
    )
    await db_session.commit()

    found = await passkeys.get_by_credential_id(b"credential-one")

    assert found is not None
    assert found.user_id == user.id
    assert found.transports == ["internal"]


async def test_count_for_user_sees_only_own_keys(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    stranger = await _user(db_session, email="other@example.org")
    passkeys = PasskeyRepository(db_session)
    await passkeys.create(
        user_id=owner.id,
        credential_id=b"one",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await passkeys.create(
        user_id=stranger.id,
        credential_id=b"two",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()

    assert await passkeys.count_for_user(owner.id) == 1


async def test_list_for_user_returns_only_own_keys(db_session: AsyncSession) -> None:
    """Список ключей показывается в личном кабинете: чужой в нём недопустим."""
    owner = await _user(db_session)
    stranger = await _user(db_session, email="other@example.org")
    passkeys = PasskeyRepository(db_session)
    mine = await passkeys.create(
        user_id=owner.id,
        credential_id=b"one",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await passkeys.create(
        user_id=stranger.id,
        credential_id=b"two",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()

    assert [item.id for item in await passkeys.list_for_user(owner.id)] == [mine.id]


async def test_deleted_key_is_gone(db_session: AsyncSession) -> None:
    """Снятый ключ не должен участвовать во входе."""
    user = await _user(db_session)
    passkeys = PasskeyRepository(db_session)
    row = await passkeys.create(
        user_id=user.id,
        credential_id=b"one",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Ключ",
    )
    await db_session.commit()

    await passkeys.delete(row)
    await db_session.commit()

    assert await passkeys.get(row.id) is None
    assert await passkeys.get_by_credential_id(b"one") is None


async def test_same_credential_id_cannot_be_registered_twice(db_session: AsyncSession) -> None:
    """Один аутентификатор — одна запись: иначе вход выбирал бы из двух."""
    user = await _user(db_session)
    passkeys = PasskeyRepository(db_session)
    await passkeys.create(
        user_id=user.id,
        credential_id=b"same",
        public_key=b"key",
        sign_count=0,
        transports=None,
        name="Первый",
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await passkeys.create(
            user_id=user.id,
            credential_id=b"same",
            public_key=b"key",
            sign_count=0,
            transports=None,
            name="Второй",
        )
