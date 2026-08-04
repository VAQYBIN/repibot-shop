"""Точка входа бота.

Вебхук — рабочий режим за Nginx. Long polling включается переменной окружения
и нужен только локально, где внешний вебхук недоступен.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from repibot_bot.handlers.start import router as start_router
from repibot_core.logging import configure_logging
from repibot_core.settings import get_settings

logger = logging.getLogger(__name__)

WEB_SERVER_HOST = "0.0.0.0"  # noqa: S104 — контейнер закрыт сетью compose, наружу смотрит nginx
WEB_SERVER_PORT = 8080


def build_dispatcher(storage: BaseStorage) -> Dispatcher:
    dispatcher = Dispatcher(storage=storage)
    dispatcher.include_router(start_router)
    return dispatcher


def _build_bot() -> Bot:
    settings = get_settings()
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def _webhook_path() -> str:
    """Секрет в пути — первый барьер: чужие запросы не доходят до разбора апдейта."""
    return f"/tg/webhook/{get_settings().bot_webhook_secret.get_secret_value()}"


def run_webhook() -> None:
    settings = get_settings()
    bot = _build_bot()
    dispatcher = build_dispatcher(RedisStorage.from_url(settings.valkey_url))

    async def on_startup(bot: Bot) -> None:
        url = f"{settings.bot_webhook_base_url}{_webhook_path()}"
        await bot.set_webhook(
            url,
            secret_token=settings.bot_webhook_secret.get_secret_value(),
            drop_pending_updates=True,
        )
        logger.info("вебхук установлен")

    dispatcher.startup.register(on_startup)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.bot_webhook_secret.get_secret_value(),
    ).register(app, path=_webhook_path())
    setup_application(app, dispatcher, bot=bot)

    web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)


def run_polling() -> None:
    async def _main() -> None:
        bot = _build_bot()
        dispatcher = build_dispatcher(RedisStorage.from_url(get_settings().valkey_url))
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)

    asyncio.run(_main())


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.bot_use_polling:
        logger.info("бот запускается в режиме long polling")
        run_polling()
    else:
        logger.info("бот запускается в режиме вебхука")
        run_webhook()


if __name__ == "__main__":
    main()
