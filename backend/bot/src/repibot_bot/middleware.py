"""Подстановка пользователя и его языка до вызова хендлера.

Хендлер не должен открывать сессию базы и разбираться, кто перед ним: иначе
это повторяется в каждом обработчике, и в одном из них забудется.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject
from redis.asyncio import Redis

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.integrations.telegram.bot_api import BotApi
from repibot_core.services.payments import PaymentService
from repibot_core.services.telegram_link import TelegramLinkService
from repibot_core.services.telegram_users import TelegramUserService
from repibot_core.settings import get_settings


class UserMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        settings = get_settings()
        # Движок один на процесс: создавать его на каждое сообщение значит
        # открывать новый пул соединений на каждое сообщение.
        self._factory = create_session_factory(create_engine(settings.database_url))
        self._settings = settings
        # Клиент Valkey тоже один на процесс и без декодирования ответов:
        # коды привязки кладёт туда API с теми же настройками.
        self._redis = Redis.from_url(settings.valkey_url, decode_responses=False)
        # BotApi держит внутри httpx-клиент, поэтому он тоже один на процесс:
        # новый на каждое сообщение открывал бы пул соединений и не закрывал его.
        self._bot_api = BotApi(settings, self._redis)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        sender = (
            event.from_user
            if isinstance(event, Message | CallbackQuery | PreCheckoutQuery)
            else None
        )
        if sender is None:
            return await handler(event, data)
        if sender.is_bot:
            # Обновление от бота обрывается здесь, а не в хендлере: строка в
            # `users` заводится ради языка, уведомлений и подписки, и ни одно
            # из них к боту не относится. Дальше его пускать некуда — без
            # `user` и `session` хендлеры всё равно не собрать, а поводы
            # получить такое обновление есть: чужой бот в супергруппе
            # поддержки и наше же сообщение, пересланное в топик.
            return None

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
            # Сессия кладётся явно: хендлерам, которые собирают сервис сами,
            # она нужна целиком, а доставать её из пользователя через
            # async_object_session — значит зависеть от того, что этот
            # объект всё ещё привязан к сессии.
            data["session"] = session
            data["telegram_users"] = service
            data["telegram_link"] = TelegramLinkService(
                session, self._settings, self._redis, self._bot_api
            )
            data["payment_service"] = PaymentService(session, self._settings)
            return await handler(event, data)
