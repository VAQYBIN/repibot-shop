"""Обработчик /start. В этом подпроекте — заглушка.

Регистрация, привязка аккаунта и кнопка запуска MiniApp появятся в подпроекте 1.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    name = message.from_user.full_name if message.from_user else "друг"
    await message.answer(f"Привет, {name}. Это Re:Pibot — магазин ещё готовится.")
