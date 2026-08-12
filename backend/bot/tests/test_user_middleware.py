"""Подстановка пользователя перед хендлером.

Проверяется граница: кого middleware вообще считает человеком и что кладёт в
данные обновления. Всё остальное — дело самих хендлеров.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from repibot_bot.middleware import UserMiddleware
from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import User, UserStatus
from repibot_core.integrations.remnawave.devices import PanelDevices


def _private_message(*, is_bot: bool) -> Message:
    return Message.model_validate(
        {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 710_001, "type": "private"},
            "from": {"id": 710_001, "is_bot": is_bot, "first_name": "Кто-то"},
            "text": "привет",
        }
    )


def _middleware(engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> UserMiddleware:
    """Middleware с базой теста вместо той, что записана в настройках."""
    middleware = UserMiddleware()
    monkeypatch.setattr(middleware, "_factory", create_session_factory(engine))
    return middleware


async def test_a_message_from_a_bot_creates_no_account(
    db_session: AsyncSession, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Бот, написавший в супергруппу поддержки, не должен получать аккаунт.

    Строка в `users` заводится ради языка, уведомлений и подписки — у бота
    ничего этого нет, а его сообщение обрабатывать некому.
    """
    handler = AsyncMock(return_value=None)
    data: dict[str, Any] = {}

    result = await _middleware(engine, monkeypatch)(handler, _private_message(is_bot=True), data)

    accounts = await db_session.scalar(select(func.count()).select_from(User))
    assert result is None
    assert accounts == 0
    handler.assert_not_awaited()


async def test_a_message_from_a_person_brings_the_account_and_the_session(
    db_session: AsyncSession, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Человек по-прежнему получает и аккаунт, и сессию для сервисов."""
    handler = AsyncMock(return_value=None)
    data: dict[str, Any] = {}

    await _middleware(engine, monkeypatch)(handler, _private_message(is_bot=False), data)

    accounts = await db_session.scalar(select(func.count()).select_from(User))
    assert accounts == 1
    assert isinstance(data["user"], User)
    assert isinstance(data["session"], AsyncSession)
    handler.assert_awaited_once()


async def test_blocked_account_stops_at_the_door(
    db_session: AsyncSession, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Бан без этого фикция: человек продолжает покупать подписку через бота.

    Проверка стоит в middleware, а не в хендлерах: их шесть, и забыть её в
    одном — значит оставить заблокированному целый сценарий.
    """
    db_session.add(
        User(
            telegram_id=710_001,
            referral_code="BLOCKED1",
            language="ru",
            status=UserStatus.banned,
        )
    )
    await db_session.commit()
    answer = AsyncMock()
    monkeypatch.setattr(Message, "answer", answer)
    handler = AsyncMock(return_value=None)
    data: dict[str, Any] = {}

    result = await _middleware(engine, monkeypatch)(handler, _private_message(is_bot=False), data)

    said = answer.await_args
    assert result is None
    handler.assert_not_awaited()
    assert answer.await_count == 1
    assert said is not None
    assert "заблокирован" in str(said.args[0]).lower()


async def test_the_devices_facade_is_one_for_the_whole_process(
    db_session: AsyncSession, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Иначе `/info` открывал бы новый пул соединений с панелью на каждый вызов."""
    del db_session
    middleware = _middleware(engine, monkeypatch)
    handler = AsyncMock(return_value=None)
    first: dict[str, Any] = {}
    second: dict[str, Any] = {}

    await middleware(handler, _private_message(is_bot=False), first)
    await middleware(handler, _private_message(is_bot=False), second)

    assert isinstance(first["panel_devices"], PanelDevices)
    assert first["panel_devices"] is second["panel_devices"]
