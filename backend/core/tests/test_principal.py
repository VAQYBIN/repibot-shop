"""Кэш роли и статуса, отметки отозванных сессий."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import UserRole, UserStatus
from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.principal import PrincipalCache

pytestmark = pytest.mark.docker


async def test_principal_is_read_from_database_then_cached(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(email="a@example.org", referral_code=await users.next_referral_code())
    await db_session.commit()
    cache = PrincipalCache(FakeRedis())

    first = await cache.get(db_session, user.id)
    user.role = UserRole.admin
    await db_session.commit()
    second = await cache.get(db_session, user.id)

    assert first is not None
    assert first.role == UserRole.user
    # Роль изменилась в базе, но кэш ещё жив: это осознанная задержка в 30 секунд.
    assert second is not None
    assert second.role == UserRole.user


async def test_invalidate_makes_change_visible(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(email="b@example.org", referral_code=await users.next_referral_code())
    await db_session.commit()
    cache = PrincipalCache(FakeRedis())
    await cache.get(db_session, user.id)

    user.status = UserStatus.banned
    await db_session.commit()
    await cache.invalidate(user.id)

    principal = await cache.get(db_session, user.id)
    assert principal is not None
    assert principal.status == UserStatus.banned


async def test_missing_user_gives_none(db_session: AsyncSession) -> None:
    cache = PrincipalCache(FakeRedis())

    assert await cache.get(db_session, 999_999) is None


async def test_revoked_session_is_remembered() -> None:
    cache = PrincipalCache(FakeRedis())
    session_id = uuid4()

    assert await cache.is_session_revoked(session_id) is False

    await cache.mark_session_revoked(session_id, ttl_seconds=900)

    assert await cache.is_session_revoked(session_id) is True
