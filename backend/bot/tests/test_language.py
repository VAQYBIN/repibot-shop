"""Выбор языка кнопками."""

from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.storage.memory import MemoryStorage

from repibot_bot.handlers.language import handle_language, handle_language_choice
from repibot_bot.main import build_dispatcher


async def test_language_command_shows_options() -> None:
    message = MagicMock()
    message.answer = AsyncMock()

    await handle_language(message, language="ru")

    markup = message.answer.await_args.kwargs["reply_markup"]
    codes = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert codes == ["lang:ru", "lang:en"]


async def test_choice_saves_language() -> None:
    callback = MagicMock()
    callback.data = "lang:en"
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.from_user.id = 777
    service = AsyncMock()

    await handle_language_choice(callback, telegram_users=service)

    service.set_language.assert_awaited_once_with(777, "en")
    assert "Language" in callback.message.edit_text.await_args.args[0]


def test_dispatcher_registers_language_router() -> None:
    dispatcher = build_dispatcher(MemoryStorage())

    assert any(router.name == "language" for router in dispatcher.sub_routers)
