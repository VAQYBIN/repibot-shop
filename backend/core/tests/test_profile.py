"""Профиль: язык, имя, пароль, адрес почты, список сессий."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.security.passwords import verify_password
from repibot_core.services.auth.password import PasswordAuth
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.services.profile import ProfileService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

PASSWORD = "совершенно обычный пароль"


def _services(session: AsyncSession) -> tuple[PasswordAuth, ProfileService]:
    settings = get_settings()
    principals = PrincipalCache(FakeRedis())
    auth = AuthService(session, settings, principals)
    letters = PasswordAuth(session, settings, auth)
    return letters, ProfileService(session, settings, auth, principals, letters)


async def _verified_user(session: AsyncSession) -> int:
    letters, _ = _services(session)
    await letters.register(email="user@example.org", password=PASSWORD, language="ru")
    messages = await OutboxRepository(session).take_batch(limit=10, now=datetime.now(UTC))
    raw = str(messages[0].payload["link"]).split("token=")[1]
    await letters.verify_email(raw, user_agent=None, ip=None)
    user = await UserRepository(session).get_by_email("user@example.org")
    assert user is not None
    return user.id


async def test_view_reports_login_methods(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    view = await profile.view(user_id)

    assert view.email == "user@example.org"
    assert view.email_verified is True
    assert view.has_password is True
    assert view.has_telegram is False
    assert view.passkey_count == 0
    assert view.referral_code


async def test_language_change_is_saved(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    updated = await profile.update(user_id, name="Имя", language="en")

    assert updated.language == "en"
    assert updated.name == "Имя"


async def test_password_change_requires_current_one(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    with pytest.raises(AuthError) as error:
        await profile.set_password(user_id, current="неверный", new="другой длинный пароль")

    assert error.value.code == "invalid_credentials"


async def test_password_change_stores_new_hash(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    await profile.set_password(user_id, current=PASSWORD, new="другой длинный пароль")

    user = await UserRepository(db_session).get(user_id)
    assert user is not None
    assert verify_password(user.password_hash, "другой длинный пароль") is True


async def test_email_change_needs_confirmation(db_session: AsyncSession) -> None:
    """Адрес меняется только после подтверждения нового.

    Иначе опечатка в адресе отбирает доступ: почта — способ входа.
    """
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    await profile.request_email_change(user_id, "new@example.org")

    user = await UserRepository(db_session).get(user_id)
    assert user is not None
    assert user.email == "user@example.org"

    messages = await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC))
    letter = next(item for item in messages if item.topic == "email.change")
    assert letter.payload["to"] == "new@example.org"

    raw = str(letter.payload["link"]).split("token=")[1]
    await profile.confirm_email_change(raw)

    user = await UserRepository(db_session).get(user_id)
    assert user is not None
    assert user.email == "new@example.org"


async def test_email_change_link_leads_to_public_page(db_session: AsyncSession) -> None:
    """Ссылка из письма не должна вести под гейт кабинета.

    Письмо открывают там, где заведена почта, а не там, где открыт кабинет.
    Страница под /account увела бы неавторизованного на вход и потеряла токен
    из адреса, поэтому подтверждение живёт в публичном разделе.
    """
    user_id = await _verified_user(db_session)
    _, profile = _services(db_session)

    await profile.request_email_change(user_id, "new@example.org")

    messages = await OutboxRepository(db_session).take_batch(limit=10, now=datetime.now(UTC))
    letter = next(item for item in messages if item.topic == "email.change")
    path = urlsplit(str(letter.payload["link"])).path
    assert path == "/confirm-email"


async def test_email_change_to_taken_address_is_refused(db_session: AsyncSession) -> None:
    first = await _verified_user(db_session)
    letters, profile = _services(db_session)
    await letters.register(email="second@example.org", password=PASSWORD, language="ru")

    with pytest.raises(AuthError) as error:
        await profile.request_email_change(first, "second@example.org")

    assert error.value.code == "email_taken"


async def test_sessions_list_marks_current(db_session: AsyncSession) -> None:
    user_id = await _verified_user(db_session)
    settings = get_settings()
    principals = PrincipalCache(FakeRedis())
    auth = AuthService(db_session, settings, principals)
    user = await UserRepository(db_session).get(user_id)
    assert user is not None
    current = await auth.issue(user, user_agent="pytest", ip="127.0.0.1", with_refresh=True)
    await auth.issue(user, user_agent="other", ip="10.0.0.1", with_refresh=True)
    _, profile = _services(db_session)

    items = await profile.list_sessions(user_id, current.session_id)

    assert len(items) == 3  # подтверждение почты выдало ещё одну
    assert [item.is_current for item in items].count(True) == 1
