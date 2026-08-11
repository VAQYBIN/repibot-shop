"""Сборка диспетчера очереди со всеми известными темами.

Отдельный модуль, потому что тем стало больше одной группы: почта не должна
знать про панель, а панель — про почту.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import EmailSender
from repibot_core.integrations.remnawave.client import create_remnawave_client
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.integrations.telegram.bot_api import BotApi
from repibot_core.services.email_dispatch import build_dispatcher as build_email_dispatcher
from repibot_core.services.notifications import (
    PAYLOAD_KEYS,
    TOPIC_NOTIFY_TELEGRAM,
    resolve_kind,
)
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.services.provisioning import TOPIC_PROVISION, build_provision_handler


def build_dispatcher(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    sender: EmailSender | None = None,
    users: PanelUsers | None = None,
    telegram: BotApi | None = None,
) -> OutboxDispatcher:
    """Диспетчер со всеми темами этапа.

    Отправитель, фасад панели и клиент бота принимаются параметрами: тест
    подставляет свои, не трогая настройки окружения, а задача — те, чьим
    временем жизни она сама и управляет.
    """
    dispatcher = build_email_dispatcher(sender)
    panel = users if users is not None else PanelUsers(create_remnawave_client())
    dispatcher.register(TOPIC_PROVISION, build_provision_handler(session_factory, panel))

    async def handle_notify_telegram(payload: dict[str, object]) -> None:
        language = str(payload["language"])
        kind = resolve_kind(str(payload["kind"]))
        # Служебные поля не попадают в текст: translate подставляет всё, что
        # получил, и лишний ключ в шаблоне даёт KeyError на живом уведомлении.
        params = {key: value for key, value in payload.items() if key not in PAYLOAD_KEYS}
        text = translate(language, f"{kind.text_key}.bot", **params)
        recipient = int(str(payload["recipient"]))
        if telegram is None:
            # Клиент живёт столько же, сколько прогон задачи, и собирается
            # вызывающим: соединение с Valkey и http-клиент на каждое
            # сообщение — это плата за каждое уведомление, а разбор очереди
            # берёт до сотни сообщений за раз. Сообщение вернётся в очередь и
            # уйдёт следующим прогоном, уже с клиентом.
            msg = "клиент бота не передан диспетчеру"
            raise RuntimeError(msg)
        await telegram.send_message(recipient, text)

    dispatcher.register(TOPIC_NOTIFY_TELEGRAM, handle_notify_telegram)
    return dispatcher
