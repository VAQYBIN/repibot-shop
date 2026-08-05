"""Репозитории: доступ к данным без бизнес-правил."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TokenType
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.sessions import SessionRepository
from repibot_core.db.repositories.tokens import TokenRepository
from repibot_core.db.repositories.users import UserRepository

pytestmark = pytest.mark.docker


async def _user(session: AsyncSession, email: str = "user@example.org") -> int:
    users = UserRepository(session)
    user = await users.create(email=email, referral_code=await users.next_referral_code())
    await session.commit()
    return user.id


async def test_user_is_found_by_normalized_email(db_session: AsyncSession) -> None:
    await _user(db_session, "user@example.org")

    found = await UserRepository(db_session).get_by_email("user@example.org")

    assert found is not None
    assert found.email == "user@example.org"


async def test_referral_code_is_unique_across_users(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    first = await users.next_referral_code()
    await users.create(email="a@example.org", referral_code=first)
    await db_session.commit()

    assert await users.next_referral_code() != first


async def test_session_rotation_keeps_previous_hash(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    sessions = SessionRepository(db_session)
    created = await sessions.create(
        user_id=user_id,
        token_hash="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        user_agent="pytest",
        ip="127.0.0.1",
    )
    await db_session.commit()

    await sessions.rotate(created, "b" * 64)
    await db_session.commit()

    assert created.refresh_token_hash == "b" * 64
    assert created.previous_token_hash == "a" * 64
    assert created.rotated_at is not None
    assert await sessions.find_by_previous_hash("a" * 64) is not None


async def test_revoke_all_keeps_current_session(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    sessions = SessionRepository(db_session)
    keep = await sessions.create(
        user_id=user_id,
        token_hash="c" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        user_agent=None,
        ip=None,
    )
    await sessions.create(
        user_id=user_id,
        token_hash="d" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        user_agent=None,
        ip=None,
    )
    await db_session.commit()

    revoked = await sessions.revoke_all(user_id, except_id=keep.id)
    await db_session.commit()

    assert len(revoked) == 1
    assert keep.id not in revoked
    assert [item.id for item in await sessions.list_active(user_id)] == [keep.id]


async def test_expired_token_is_not_usable(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    tokens = TokenRepository(db_session)
    await tokens.create(
        type=TokenType.email_verify,
        user_id=user_id,
        token_hash="e" * 64,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    await db_session.commit()

    found = await tokens.find_usable(TokenType.email_verify, "e" * 64, datetime.now(UTC))

    assert found is None


async def test_used_token_is_not_usable_twice(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)
    tokens = TokenRepository(db_session)
    token = await tokens.create(
        type=TokenType.password_reset,
        user_id=user_id,
        token_hash="f" * 64,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    await db_session.commit()

    await tokens.mark_used(token)
    await db_session.commit()

    assert await tokens.find_usable(TokenType.password_reset, "f" * 64, datetime.now(UTC)) is None


async def test_outbox_batch_skips_postponed_messages(db_session: AsyncSession) -> None:
    outbox = OutboxRepository(db_session)
    ready = await outbox.add("email.verify", {"to": "a@example.org"})
    later = await outbox.add(
        "email.verify",
        {"to": "b@example.org"},
        available_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    await db_session.commit()

    batch = await outbox.take_batch(limit=10, now=datetime.now(UTC))

    assert [item.id for item in batch] == [ready.id]
    assert later.id not in [item.id for item in batch]


async def test_processed_message_is_not_taken_again(db_session: AsyncSession) -> None:
    outbox = OutboxRepository(db_session)
    message = await outbox.add("email.verify", {"to": "a@example.org"})
    await db_session.commit()

    await outbox.mark_processed(message)
    await db_session.commit()

    assert await outbox.take_batch(limit=10, now=datetime.now(UTC)) == []


async def test_audit_record_is_written(db_session: AsyncSession) -> None:
    user_id = await _user(db_session)

    await AuditRepository(db_session).record(
        "role.granted", "user", actor_id=None, entity_id=str(user_id), after={"role": "admin"}
    )
    await db_session.commit()
