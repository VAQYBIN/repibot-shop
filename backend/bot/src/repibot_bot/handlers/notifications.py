"""Отписка от маркетинга кнопкой под сообщением бота.

Кнопку ставит разбор очереди, нажатие приходит сюда. Отдельный роутер, а не
ветка в `language`: у этих кнопок разная цена ошибки — не тот язык человек
переключит обратно, а не ту отписку он заметит только по тишине.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import async_object_session

from repibot_core.db.models import User
from repibot_core.i18n import translate
from repibot_core.services.unsubscribe import (
    CALLBACK_DATA,
    UnsubscribeService,
    sign_unsubscribe_token,
)


async def handle_unsubscribe(callback: CallbackQuery, user: User, language: str) -> None:
    """Отписывает нажавшего и подтверждает всплывающим окном.

    Токен подписывается на месте, хотя пользователь уже известен: отписку по
    всем каналам делает один сервис, и второй путь к тому же полю разошёлся бы
    с первым на первой же правке.
    """
    session = async_object_session(user)
    if session is None:  # сессия закрыта — сообщение стоит повторить, а не солгать
        await callback.answer()
        return

    await UnsubscribeService(session).apply(sign_unsubscribe_token(user.id))
    await session.commit()
    # show_alert, а не подсказка сверху: она гаснет за секунду, и человек не
    # успевает прочитать, что сервисные сообщения остались.
    await callback.answer(translate(language, "notify.unsubscribed"), show_alert=True)


def build_notifications_router() -> Router:
    router = Router(name="notifications")
    router.callback_query.register(handle_unsubscribe, F.data == CALLBACK_DATA)
    return router
