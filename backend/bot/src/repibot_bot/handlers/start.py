"""Обработчик /start. В этом подпроекте — заглушка.

Регистрация, привязка аккаунта и кнопка запуска MiniApp появятся в подпроекте 1.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message


async def handle_start(message: Message) -> None:
    name = message.from_user.full_name if message.from_user else "друг"
    await message.answer(f"Привет, {name}. Это Re:Pibot — магазин ещё готовится.")


def build_start_router() -> Router:
    """Новый роутер на каждый вызов.

    aiogram запрещает подключать один экземпляр Router к двум диспетчерам,
    а модульный синглтон делает второй Dispatcher в процессе невозможным.
    """
    router = Router(name="start")
    router.message.register(handle_start, CommandStart())
    return router
