"""Переключение языка."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from repibot_core.i18n import translate
from repibot_core.services.telegram_users import TelegramUserService

_TITLES = {"ru": "Русский", "en": "English"}


async def handle_language(message: Message, language: str) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"lang:{code}")]
            for code, title in _TITLES.items()
        ]
    )
    await message.answer(translate(language, "bot.language.choose"), reply_markup=keyboard)


async def handle_language_choice(
    callback: CallbackQuery, telegram_users: TelegramUserService
) -> None:
    chosen = (callback.data or "").removeprefix("lang:")
    if chosen not in _TITLES:
        await callback.answer()
        return

    await telegram_users.set_language(callback.from_user.id, chosen)
    # Подтверждение приходит уже на новом языке: иначе непонятно, сработало ли.
    # InaccessibleMessage отсеивается отдельно: у слишком старого сообщения,
    # которое Telegram уже не отдаёт, метода правки нет вовсе.
    message = callback.message
    if message is not None and not isinstance(message, InaccessibleMessage):
        await message.edit_text(translate(chosen, "bot.language.saved"))
    await callback.answer()


def build_language_router() -> Router:
    router = Router(name="language")
    router.message.register(handle_language, Command("language"))
    router.callback_query.register(handle_language_choice, F.data.startswith("lang:"))
    return router
