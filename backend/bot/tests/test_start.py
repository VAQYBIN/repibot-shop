"""Хендлер проверяется напрямую: поднимать Telegram ради проверки текста незачем."""

from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.storage.memory import MemoryStorage

from repibot_bot.handlers.start import handle_start
from repibot_bot.main import build_dispatcher


async def test_start_greets_user_by_name() -> None:
    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user.full_name = "Иван"

    await handle_start(message)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Иван" in text
    assert "Re:Pibot" in text


async def test_start_survives_missing_from_user() -> None:
    """Сообщения от каналов приходят без from_user — падать на этом нельзя."""
    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user = None

    await handle_start(message)

    message.answer.assert_awaited_once()


def test_dispatcher_registers_start_router() -> None:
    dispatcher = build_dispatcher(MemoryStorage())

    assert any(router.name == "start" for router in dispatcher.sub_routers)
