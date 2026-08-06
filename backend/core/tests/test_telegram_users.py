"""Создание пользователя по обращению в бот."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.telegram_users import TelegramUserService
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


async def test_first_start_creates_user(db_session: AsyncSession) -> None:
    service = TelegramUserService(db_session, get_settings())

    user = await service.ensure(777, username="ivan", first_name="Иван", language_code="ru")

    assert user.telegram_id == 777
    assert user.language == "ru"
    assert user.referral_code


async def test_second_start_returns_the_same_user(db_session: AsyncSession) -> None:
    service = TelegramUserService(db_session, get_settings())
    first = await service.ensure(777, username="ivan", first_name="Иван", language_code="ru")

    second = await service.ensure(777, username="ivan_new", first_name="Иван", language_code="ru")

    assert second.id == first.id
    assert second.telegram_username == "ivan_new"


async def test_unsupported_language_falls_back(db_session: AsyncSession) -> None:
    service = TelegramUserService(db_session, get_settings())

    user = await service.ensure(778, username=None, first_name="Hans", language_code="de")

    assert user.language == get_settings().default_language


async def test_language_is_saved(db_session: AsyncSession) -> None:
    service = TelegramUserService(db_session, get_settings())
    await service.ensure(779, username=None, first_name=None, language_code="ru")

    await service.set_language(779, "en")

    user = await UserRepository(db_session).get_by_telegram_id(779)
    assert user is not None
    assert user.language == "en"
