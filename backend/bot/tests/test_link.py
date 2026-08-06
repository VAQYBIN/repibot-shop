"""Бот принимает код привязки и отвечает по-человечески."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiogram import Router
from aiogram.filters import CommandObject
from aiogram.types import Chat, Message

from repibot_bot.handlers.start import build_start_router, handle_link_start, handle_start
from repibot_core.db.models import User
from repibot_core.services.auth.types import AuthError


class FakeLinks:
    """Сервис привязки без базы: хендлер проверяется отдельно от неё."""

    def __init__(self, error: AuthError | None = None) -> None:
        self.error = error
        self.seen: dict[str, Any] = {}

    async def redeem(
        self, code: str, *, telegram_id: int, username: str | None, first_name: str | None
    ) -> User:
        self.seen = {
            "code": code,
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
        }
        if self.error is not None:
            raise self.error
        return User(id=1, referral_code="AAAABBBB", language="ru")


def _message() -> AsyncMock:
    message = AsyncMock()
    message.from_user.id = 555
    message.from_user.username = "tester"
    message.from_user.first_name = "Тест"
    return message


def _user() -> User:
    return User(id=1, referral_code="AAAABBBB", language="ru")


async def _reply(links: FakeLinks, args: str | None) -> str:
    message = _message()
    await handle_link_start(
        message,
        CommandObject(command="start", args=args),
        _user(),
        "ru",
        links,
    )
    text = message.answer.await_args.args[0]
    assert isinstance(text, str)
    return text


async def test_valid_code_reports_success() -> None:
    links = FakeLinks()

    text = await _reply(links, "link_ABC123")

    assert links.seen == {
        "code": "ABC123",
        "telegram_id": 555,
        "username": "tester",
        "first_name": "Тест",
    }
    assert "привязан" in text.lower()


async def test_conflict_is_explained_not_silent() -> None:
    """Отказ должен объяснять, что делать, а не сообщать код ошибки."""
    links = FakeLinks(AuthError("link_conflict", "у этого Telegram есть свой аккаунт"))

    text = await _reply(links, "link_ABC123")

    assert "уже" in text.lower()
    assert "link_conflict" not in text


async def test_second_link_of_the_same_telegram_is_not_an_error() -> None:
    """Повторное предъявление кода тем же человеком сервис считает успехом."""
    links = FakeLinks(AuthError("telegram_already_linked", "к аккаунту привязан другой Telegram"))

    text = await _reply(links, "link_ABC123")

    assert "уже" in text.lower()


async def test_expired_code_says_to_take_a_new_one() -> None:
    links = FakeLinks(AuthError("token_invalid", "код устарел"))

    text = await _reply(links, "link_OLD123")

    assert "новый код" in text.lower()


async def test_empty_code_does_not_reach_the_service() -> None:
    """Пустая глубокая ссылка — не повод открывать сессию Valkey."""
    links = FakeLinks()

    text = await _reply(links, "link_")

    assert links.seen == {}
    assert "новый код" in text.lower()


async def test_answers_in_the_user_language() -> None:
    message = _message()

    await handle_link_start(
        message,
        CommandObject(command="start", args="link_ABC123"),
        _user(),
        "en",
        FakeLinks(),
    )

    assert "linked" in message.answer.await_args.args[0].lower()


def _text_message(text: str) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=1, type="private"),
        text=text,
    )


async def _first_match(router: Router, text: str) -> Callable[..., Any] | None:
    """Возвращает первый хендлер роутера, чьи фильтры пропустили сообщение.

    Так же выбирает обработчик и сам aiogram, поэтому порядок регистрации
    проверяется здесь на самом деле, а не на глаз.
    """
    for handler in router.message.handlers:
        passed, _ = await handler.check(_text_message(text), bot=MagicMock())
        if passed:
            return handler.callback
    return None


async def test_deep_link_wins_over_the_greeting() -> None:
    """Если обычный /start зарегистрирован первым, он молча проглотит код."""
    assert await _first_match(build_start_router(), "/start link_ABC123") is handle_link_start


async def test_plain_start_still_greets() -> None:
    assert await _first_match(build_start_router(), "/start") is handle_start


async def test_foreign_deep_link_goes_to_the_greeting() -> None:
    """Реферальные и прочие ссылки не должны попадать в привязку."""
    assert await _first_match(build_start_router(), "/start ref_ABC123") is handle_start
