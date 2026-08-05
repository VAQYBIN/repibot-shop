"""Подстановка пользователя и его языка до вызова хендлера.

Хендлер не должен открывать сессию базы и разбираться, кто перед ним: иначе
это повторяется в каждом обработчике, и в одном из них забудется.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.services.telegram_users import TelegramUserService
from repibot_core.settings import get_settings


class UserMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        settings = get_settings()
        # Движок один на процесс: создавать его на каждое сообщение значит
        # открывать новый пул соединений на каждое сообщение.
        self._factory = create_session_factory(create_engine(settings.database_url))
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender = event.from_user if isinstance(event, Message | CallbackQuery) else None
        if sender is None:
            return await handler(event, data)

        async with self._factory() as session:
            service = TelegramUserService(session, self._settings)
            user = await service.ensure(
                sender.id,
                username=sender.username,
                first_name=sender.first_name,
                language_code=sender.language_code,
            )
            data["user"] = user
            data["language"] = user.language
            data["telegram_users"] = service
            return await handler(event, data)
