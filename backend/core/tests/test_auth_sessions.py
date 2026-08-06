"""Выдача, ротация и отзыв сессий."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User, UserStatus
from repibot_core.db.repositories.sessions import SessionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.tokens import decode_access_token
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


async def _service(session: AsyncSession) -> AuthService:
    return AuthService(session, get_settings(), PrincipalCache(FakeRedis()))


async def _user(session: AsyncSession, **fields: object) -> User:
    users = UserRepository(session)
    user = await users.create(
        email="user@example.org", referral_code=await users.next_referral_code(), **fields
    )
    await session.commit()
    return user


async def test_issue_returns_working_access_token(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)

    issued = await service.issue(user, user_agent="pytest", ip="127.0.0.1", with_refresh=True)

    claims = decode_access_token(
        issued.access_token, secret=get_settings().jwt_secret.get_secret_value()
    )
    assert claims.user_id == user.id
    assert claims.session_id == issued.session_id
    assert issued.refresh_token is not None


async def test_miniapp_session_has_no_refresh(db_session: AsyncSession) -> None:
    """В MiniApp cookie не выживает: refresh там не выдаётся вовсе."""
    user = await _user(db_session)
    service = await _service(db_session)

    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=False)

    assert issued.refresh_token is None


async def test_refresh_rotates_token(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None

    rotated = await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    assert rotated.refresh_token is not None
    assert rotated.refresh_token != issued.refresh_token
    assert rotated.session_id == issued.session_id


async def test_previous_token_works_inside_race_window(db_session: AsyncSession) -> None:
    """Две вкладки обновляют токен одновременно — обе должны остаться в системе."""
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None
    await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    again = await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    assert again.refresh_token is not None


async def test_previous_token_after_window_revokes_session(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None
    rotated = await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    session_row = await SessionRepository(db_session).get(issued.session_id)
    assert session_row is not None
    session_row.rotated_at = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.commit()

    with pytest.raises(AuthError) as error:
        await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    assert error.value.code == "token_invalid"
    # Утечка означает, что и текущий токен считать своим больше нельзя.
    assert rotated.refresh_token is not None
    with pytest.raises(AuthError):
        await service.refresh(rotated.refresh_token, user_agent=None, ip=None)


async def test_unknown_token_is_rejected(db_session: AsyncSession) -> None:
    service = await _service(db_session)

    with pytest.raises(AuthError) as error:
        await service.refresh("никогда не выдавался", user_agent=None, ip=None)

    assert error.value.code == "token_invalid"


async def test_expired_session_is_rejected(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None

    row = await SessionRepository(db_session).get(issued.session_id)
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()

    with pytest.raises(AuthError):
        await service.refresh(issued.refresh_token, user_agent=None, ip=None)


async def test_banned_user_cannot_refresh(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    issued = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    assert issued.refresh_token is not None

    user.status = UserStatus.banned
    await db_session.commit()

    with pytest.raises(AuthError) as error:
        await service.refresh(issued.refresh_token, user_agent=None, ip=None)

    assert error.value.code == "forbidden"


async def test_logout_revokes_only_current_session(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    service = await _service(db_session)
    first = await service.issue(user, user_agent=None, ip=None, with_refresh=True)
    second = await service.issue(user, user_agent=None, ip=None, with_refresh=True)

    await service.logout(first.session_id)

    active = [item.id for item in await SessionRepository(db_session).list_active(user.id)]
    assert active == [second.session_id]
