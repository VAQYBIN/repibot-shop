"""Приветствие с кнопкой запуска MiniApp и привязка по глубокой ссылке.

Оба сценария начинаются с `/start`, поэтому живут в одном модуле: их фильтры
различаются только аргументом команды, и порядок регистрации важен.
"""

from __future__ import annotations

from typing import Protocol

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from repibot_core.db.models import User
from repibot_core.i18n import translate
from repibot_core.services.auth.types import AuthError
from repibot_core.settings import get_settings

LINK_PREFIX = "link_"

# Человеку нужен не код ошибки, а следующий шаг. Коды, которых здесь нет,
# сводятся к «код не подошёл»: пропавший аккаунт и просроченный код неотличимы
# для того, кто просто нажал на ссылку.
_LINK_REPLIES = {
    "link_conflict": "bot.link.conflict",
    "telegram_already_linked": "bot.link.already",
    "token_invalid": "bot.link.expired",
}


class LinkRedeemer(Protocol):
    """Всё, что хендлеру нужно от сервиса привязки.

    Протокол — чтобы тест хендлера обходился без базы и Valkey.
    """

    async def redeem(
        self, code: str, *, telegram_id: int, username: str | None, first_name: str | None
    ) -> User: ...


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


async def handle_link_start(
    message: Message,
    command: CommandObject,
    user: User,
    language: str,
    telegram_link: LinkRedeemer,
) -> None:
    """Привязка по глубокой ссылке `t.me/<bot>?start=link_XXX`.

    Пользователь к этому моменту уже создан middleware — если он пришёл сюда
    впервые, это и есть тот самый пустой дубль, который сервис поглотит.
    """
    code = (command.args or "").removeprefix(LINK_PREFIX)
    sender = message.from_user
    if not code or sender is None:
        await message.answer(translate(language, "bot.link.expired"))
        return

    try:
        await telegram_link.redeem(
            code,
            telegram_id=sender.id,
            username=sender.username,
            first_name=sender.first_name,
        )
    except AuthError as error:
        await message.answer(translate(language, _LINK_REPLIES.get(error.code, "bot.link.expired")))
        return

    await message.answer(translate(language, "bot.link.done"))


def build_start_router() -> Router:
    """Новый роутер на каждый вызов.

    aiogram запрещает подключать один экземпляр Router к двум диспетчерам,
    а модульный синглтон делает второй Dispatcher в процессе невозможным.
    """
    router = Router(name="start")
    # Глубокая ссылка проверяется первой: обычный /start принял бы её как
    # приветствие и молча проглотил код.
    router.message.register(
        handle_link_start, CommandStart(deep_link=True, magic=F.args.regexp(f"^{LINK_PREFIX}"))
    )
    router.message.register(handle_start, CommandStart())
    return router
