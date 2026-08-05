"""Регистрация и вход паролем."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import TokenType
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.tokens import TokenRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.tokens import hash_opaque_token
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.email_dispatch import TOPIC_EMAIL_VERIFY
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


def _auth(session: AsyncSession) -> PasswordAuth:
    settings = get_settings()
    return PasswordAuth(
        session, settings, AuthService(session, settings, PrincipalCache(FakeRedis()))
    )


async def _token_from_outbox(session: AsyncSession, topic: str) -> str:
    """Достаёт токен из ссылки в поставленном письме.

    Тест ходит тем же путём, что и пользователь: у сервиса нет метода, который
    вернул бы токен напрямую, — иначе он появился бы и в продакшене.
    """
    messages = await OutboxRepository(session).take_batch(limit=10, now=datetime.now(UTC))
    letter = next(item for item in messages if item.topic == topic)
    link = str(letter.payload["link"])
    return link.split("token=")[1]


async def test_registration_creates_user_and_queues_letter(db_session: AsyncSession) -> None:
    await _auth(db_session).register(email="User@Example.ORG", password=PASSWORD, language="ru")

    user = await UserRepository(db_session).get_by_email("user@example.org")
    assert user is not None
    assert user.email == "user@example.org"
    assert user.email_verified_at is None
    assert user.password_hash is not None
    assert user.referral_code

    messages = await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC))
    assert [item.topic for item in messages] == [TOPIC_EMAIL_VERIFY]
    assert messages[0].payload["to"] == "user@example.org"


async def test_login_before_verification_is_refused(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")

    with pytest.raises(AuthError) as error:
        await auth.login(email="user@example.org", password=PASSWORD, user_agent=None, ip=None)

    assert error.value.code == "email_not_verified"


async def test_verification_lets_user_in(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)

    issued = await auth.verify_email(raw, user_agent=None, ip=None)

    assert issued.access_token
    user = await UserRepository(db_session).get_by_email("user@example.org")
    assert user is not None
    assert user.email_verified_at is not None


async def test_verification_token_works_once(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    await auth.verify_email(raw, user_agent=None, ip=None)

    with pytest.raises(AuthError) as error:
        await auth.verify_email(raw, user_agent=None, ip=None)

    assert error.value.code == "token_invalid"


async def test_login_with_wrong_password_and_unknown_email_look_alike(
    db_session: AsyncSession,
) -> None:
    """Ответ не должен сообщать, зарегистрирован ли адрес."""
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    await auth.verify_email(raw, user_agent=None, ip=None)

    with pytest.raises(AuthError) as wrong:
        await auth.login(
            email="user@example.org", password="другой пароль", user_agent=None, ip=None
        )
    with pytest.raises(AuthError) as unknown:
        await auth.login(email="nobody@example.org", password=PASSWORD, user_agent=None, ip=None)

    assert wrong.value.code == unknown.value.code == "invalid_credentials"


async def test_second_registration_on_verified_email_is_refused(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    await auth.verify_email(raw, user_agent=None, ip=None)

    with pytest.raises(AuthError) as error:
        await auth.register(email="user@example.org", password=PASSWORD, language="ru")

    assert error.value.code == "email_taken"


async def test_registration_on_unverified_email_resends_letter(db_session: AsyncSession) -> None:
    """Неподтверждённый аккаунт не должен занимать адрес навсегда.

    Опечатка в пароле при регистрации, закрытая вкладка, потерянное письмо —
    человек повторяет регистрацию, и это должно работать.
    """
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")

    await auth.register(email="user@example.org", password="другой длинный пароль", language="en")

    users = await UserRepository(db_session).get_by_email("user@example.org")
    assert users is not None
    assert users.language == "en"
    messages = await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC))
    assert len(messages) == 2


async def test_weak_password_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(AuthError) as error:
        await _auth(db_session).register(
            email="user@example.org", password="короткий", language="ru"
        )

    assert error.value.code == "weak_password"


async def test_reset_replaces_password_and_revokes_sessions(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    verify = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    old_session = await auth.verify_email(verify, user_agent=None, ip=None)

    await auth.request_reset("user@example.org")
    raw = await _token_from_outbox(db_session, "email.password_reset")
    await auth.reset(raw, "новый совершенно обычный пароль", user_agent=None, ip=None)

    await auth.login(
        email="user@example.org",
        password="новый совершенно обычный пароль",
        user_agent=None,
        ip=None,
    )
    assert old_session.refresh_token is not None
    with pytest.raises(AuthError):
        # Обращение к внутреннему AuthService намеренное: отзыв сессий проверяется
        # тем же вызовом, которым её обновляет браузер.
        await auth._auth.refresh(old_session.refresh_token, user_agent=None, ip=None)


async def test_reset_for_unknown_email_is_silent(db_session: AsyncSession) -> None:
    """Ответ одинаковый, письма нет: иначе форма превращается в проверку адресов."""
    await _auth(db_session).request_reset("nobody@example.org")

    assert await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC)) == []


async def test_second_reset_request_kills_the_first_link(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    verify = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    await auth.verify_email(verify, user_agent=None, ip=None)

    await auth.request_reset("user@example.org")
    first = await _token_from_outbox(db_session, "email.password_reset")
    await auth.request_reset("user@example.org")

    tokens = TokenRepository(db_session)
    assert (
        await tokens.find_usable(
            TokenType.password_reset, hash_opaque_token(first), datetime.now(UTC)
        )
        is None
    )


async def test_expired_verification_token_is_refused(db_session: AsyncSession) -> None:
    auth = _auth(db_session)
    await auth.register(email="user@example.org", password=PASSWORD, language="ru")
    raw = await _token_from_outbox(db_session, TOPIC_EMAIL_VERIFY)
    token = await TokenRepository(db_session).find_usable(
        TokenType.email_verify, hash_opaque_token(raw), datetime.now(UTC)
    )
    assert token is not None
    token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    with pytest.raises(AuthError):
        await auth.verify_email(raw, user_agent=None, ip=None)
