"""Вход через Telegram: MiniApp и браузер через OIDC."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.users import UserRepository
from repibot_core.integrations.telegram.oidc import OidcIdentity
from repibot_core.security.tokens import decode_access_token
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


async def test_oidc_login_reuses_the_miniapp_account(db_session: AsyncSession) -> None:
    """Один Telegram — один аккаунт, откуда бы человек ни вошёл."""
    telegram = _telegram(db_session)
    first = await telegram.login_from_miniapp(
        build_init_data(bot_token=BOT_TOKEN, telegram_id=777000), ip=None
    )

    second = await telegram.login_from_oidc(
        OidcIdentity(telegram_id=777000, username="tester", name="Тест"),
        user_agent="Firefox",
        ip="127.0.0.1",
    )

    secret = get_settings().jwt_secret.get_secret_value()
    assert decode_access_token(first.access_token, secret=secret).user_id == (
        decode_access_token(second.access_token, secret=secret).user_id
    )
    # Сессии всё же разные: это два разных устройства.
    assert first.session_id != second.session_id


async def test_oidc_login_issues_refresh_unlike_miniapp(db_session: AsyncSession) -> None:
    """В обычном браузере cookie живёт, поэтому refresh выдаётся."""
    issued = await _telegram(db_session).login_from_oidc(
        OidcIdentity(telegram_id=42, username=None, name=None), user_agent=None, ip=None
    )

    assert issued.refresh_token is not None


async def test_oidc_login_updates_username(db_session: AsyncSession) -> None:
    """@username меняется на стороне Telegram — обновляем при каждом входе."""
    telegram = _telegram(db_session)
    await telegram.login_from_oidc(
        OidcIdentity(telegram_id=42, username="old", name="Тест"), user_agent=None, ip=None
    )

    await telegram.login_from_oidc(
        OidcIdentity(telegram_id=42, username="new", name="Тест"), user_agent=None, ip=None
    )

    user = await UserRepository(db_session).get_by_telegram_id(42)
    assert user is not None
    assert user.telegram_username == "new"


async def test_oidc_login_without_username_creates_account(db_session: AsyncSession) -> None:
    """Скрытый @username — не повод отказать: обязателен только sub из ID-токена."""
    await _telegram(db_session).login_from_oidc(
        OidcIdentity(telegram_id=99, username=None, name=None), user_agent=None, ip=None
    )

    user = await UserRepository(db_session).get_by_telegram_id(99)
    assert user is not None
    assert user.telegram_username is None
    # Язык из OIDC не приходит — берётся значение по умолчанию, а не пустое.
    assert user.language == get_settings().default_language


async def test_banned_user_cannot_sign_in_through_oidc(db_session: AsyncSession) -> None:
    """Статус проверяет AuthService: браузерный вход его не обходит."""
    from repibot_core.db.models import UserStatus

    telegram = _telegram(db_session)
    await telegram.login_from_oidc(
        OidcIdentity(telegram_id=555, username=None, name=None), user_agent=None, ip=None
    )
    user = await UserRepository(db_session).get_by_telegram_id(555)
    assert user is not None
    user.status = UserStatus.banned
    await db_session.commit()

    with pytest.raises(AuthError) as error:
        await telegram.login_from_oidc(
            OidcIdentity(telegram_id=555, username=None, name=None), user_agent=None, ip=None
        )

    assert error.value.code == "forbidden"
