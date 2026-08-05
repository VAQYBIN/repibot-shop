"""Вход из MiniApp: создание аккаунта по telegram_id и повторный вход."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.auth.service import AuthService
from repibot_core.services.auth.telegram import TelegramAuth
from repibot_core.services.auth.types import AuthError
from repibot_core.services.principal import PrincipalCache
from repibot_core.settings import get_settings
from repibot_core.testing.initdata import build_init_data

pytestmark = pytest.mark.docker

BOT_TOKEN = "123456:test-token"


def _telegram(session: AsyncSession) -> TelegramAuth:
    settings = get_settings()
    return TelegramAuth(
        session, settings, AuthService(session, settings, PrincipalCache(FakeRedis()))
    )


async def test_first_open_creates_account(db_session: AsyncSession) -> None:
    issued = await _telegram(db_session).login_from_miniapp(
        build_init_data(bot_token=BOT_TOKEN), ip="127.0.0.1"
    )

    assert issued.access_token
    # В MiniApp cookie не выживает — refresh не выдаётся.
    assert issued.refresh_token is None

    user = await UserRepository(db_session).get_by_telegram_id(777)
    assert user is not None
    assert user.language == "ru"
    assert user.email is None
    assert user.referral_code


async def test_second_open_reuses_account(db_session: AsyncSession) -> None:
    telegram = _telegram(db_session)
    first = await telegram.login_from_miniapp(build_init_data(bot_token=BOT_TOKEN), ip=None)

    second = await telegram.login_from_miniapp(build_init_data(bot_token=BOT_TOKEN), ip=None)

    assert first.session_id != second.session_id
    users = UserRepository(db_session)
    assert await users.get_by_telegram_id(777) is not None


async def test_username_is_refreshed_on_login(db_session: AsyncSession) -> None:
    """Имя пользователя меняется на стороне Telegram, и мы обязаны догонять."""
    telegram = _telegram(db_session)
    await telegram.login_from_miniapp(build_init_data(bot_token=BOT_TOKEN), ip=None)

    await telegram.login_from_miniapp(
        build_init_data(bot_token=BOT_TOKEN, username="ivan_new"), ip=None
    )

    user = await UserRepository(db_session).get_by_telegram_id(777)
    assert user is not None
    assert user.telegram_username == "ivan_new"


async def test_tampered_init_data_is_refused(db_session: AsyncSession) -> None:
    with pytest.raises(AuthError) as error:
        await _telegram(db_session).login_from_miniapp("hash=подделка", ip=None)

    assert error.value.code == "invalid_credentials"


async def test_admin_from_env_gets_role(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "777")
    get_settings.cache_clear()

    await _telegram(db_session).login_from_miniapp(build_init_data(bot_token=BOT_TOKEN), ip=None)

    user = await UserRepository(db_session).get_by_telegram_id(777)
    assert user is not None
    assert user.role.value == "admin"

    get_settings.cache_clear()
