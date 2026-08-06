"""Хендлер проверяется напрямую: поднимать Telegram ради проверки текста незачем."""

from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message

from repibot_bot.handlers.start import handle_start
from repibot_bot.main import build_dispatcher
from repibot_bot.middleware import UserMiddleware


async def test_start_greets_user_by_name() -> None:
    message = MagicMock()
    message.answer = AsyncMock()
    user = MagicMock()
    user.name = "Иван"

    await handle_start(message, user=user, language="ru")

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Иван" in text
    assert "Re:Pibot" in text


async def test_start_offers_the_app() -> None:
    """Кнопка запуска MiniApp — единственный вход в магазин из бота."""
    message = MagicMock()
    message.answer = AsyncMock()

    await handle_start(message, user=MagicMock(name="Иван"), language="ru")

    markup = message.answer.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].web_app is not None


async def test_start_answers_in_user_language() -> None:
    message = MagicMock()
    message.answer = AsyncMock()

    await handle_start(message, user=MagicMock(), language="en")

    assert "Hello" in message.answer.await_args.args[0]


async def test_middleware_passes_through_events_without_sender() -> None:
    """Сообщения от каналов приходят без from_user — падать на этом нельзя."""
    middleware = UserMiddleware()
    handler = AsyncMock()
    event = MagicMock(spec=Message)
    event.from_user = None

    await middleware(handler, event, {})

    handler.assert_awaited_once()


def test_dispatcher_registers_start_router() -> None:
    dispatcher = build_dispatcher(MemoryStorage())

    assert any(router.name == "start" for router in dispatcher.sub_routers)
