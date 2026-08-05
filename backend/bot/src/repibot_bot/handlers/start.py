"""Приветствие и кнопка запуска MiniApp."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from repibot_core.db.models import User
from repibot_core.i18n import translate
from repibot_core.settings import get_settings


async def handle_start(message: Message, user: User, language: str) -> None:
    name = user.name or (message.from_user.full_name if message.from_user else "")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate(language, "bot.start.open_app"),
                    web_app=WebAppInfo(url=get_settings().public_app_url),
                )
            ]
        ]
    )
    await message.answer(
        translate(language, "bot.start.greeting", name=name), reply_markup=keyboard
    )


def build_start_router() -> Router:
    """Новый роутер на каждый вызов.

    aiogram запрещает подключать один экземпляр Router к двум диспетчерам,
    а модульный синглтон делает второй Dispatcher в процессе невозможным.
    """
    router = Router(name="start")
    router.message.register(handle_start, CommandStart())
    return router
