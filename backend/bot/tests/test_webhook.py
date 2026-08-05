"""Путь вебхука — часть публичного контракта развёртывания, секретов в нём нет."""

from aiogram import Bot
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp.test_utils import TestClient, TestServer

from repibot_bot.main import WEBHOOK_PATH, build_dispatcher, build_web_app
from repibot_core.settings import get_settings


def test_webhook_path_is_grouped_under_common_prefix() -> None:
    """Вебхуки живут под /webhook/<источник>: за Telegram придёт YooKassa."""
    assert WEBHOOK_PATH == "/webhook/telegram"


def test_webhook_path_does_not_contain_the_secret() -> None:
    """URL целиком попадает в журналы прокси, ngrok и мониторинга.

    Подлинность запроса подтверждает заголовок, а не путь, поэтому секрету
    в адресе делать нечего.
    """
    secret = get_settings().bot_webhook_secret.get_secret_value()

    assert secret not in WEBHOOK_PATH


async def test_webhook_rejects_request_without_secret_header() -> None:
    """Единственная защита эндпоинта — заголовок. Проверяем, что она работает."""
    bot = Bot(token=get_settings().bot_token.get_secret_value())
    app = build_web_app(bot, build_dispatcher(MemoryStorage()))

    async with TestClient(TestServer(app)) as client:
        response = await client.post(WEBHOOK_PATH, json={"update_id": 1})

    await bot.session.close()

    assert response.status == 401


async def test_webhook_accepts_request_with_correct_secret_header() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token.get_secret_value())
    app = build_web_app(bot, build_dispatcher(MemoryStorage()))

    # Обычное сообщение, а не команда: ни один обработчик не сработает,
    # и проверяется ровно приём запроса, без обращений к Telegram.
    update = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 1, "type": "private"},
            "text": "просто текст",
        },
    }

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            WEBHOOK_PATH,
            json=update,
            headers={
                "X-Telegram-Bot-Api-Secret-Token": settings.bot_webhook_secret.get_secret_value()
            },
        )

    await bot.session.close()

    assert response.status == 200
