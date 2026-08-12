"""Сборка диспетчера очереди со всеми известными темами.

Отдельный модуль, потому что тем стало больше одной группы: почта не должна
знать про панель, а панель — про почту.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.db.models import Ticket
from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import EmailSender
from repibot_core.integrations.remnawave.client import create_remnawave_client
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.integrations.telegram.bot_api import BotApi
from repibot_core.integrations.telegram.support_chat import SupportChat
from repibot_core.services.email_dispatch import build_dispatcher as build_email_dispatcher
from repibot_core.services.notifications import (
    PAYLOAD_KEYS,
    TOPIC_NOTIFY_TELEGRAM,
    NotificationCategory,
    resolve_kind,
)
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.services.provisioning import TOPIC_PROVISION, build_provision_handler
from repibot_core.services.support import TOPIC_SUPPORT_OUTBOUND, topic_name
from repibot_core.services.support_card import build_card, devices_for_card
from repibot_core.services.unsubscribe import CALLBACK_DATA


def build_dispatcher(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    sender: EmailSender | None = None,
    users: PanelUsers | None = None,
    telegram: BotApi | None = None,
    support: SupportChat | None = None,
    panel_devices: PanelDevices | None = None,
) -> OutboxDispatcher:
    """Диспетчер со всеми темами этапа.

    Отправитель, фасад панели и клиент бота принимаются параметрами: тест
    подставляет свои, не трогая настройки окружения, а задача — те, чьим
    временем жизни она сама и управляет.

    Фасад устройств необязателен отдельно от фасада пользователей: без него
    карточка собеседника выходит с «н/д», и это лучше, чем несозданная тема.
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

        markup: dict[str, object] | None = None
        if kind.category is NotificationCategory.marketing:
            # Отписка обязана быть на расстоянии одного касания: иначе человек
            # блокирует бота, и вместе с предложениями теряются сообщения о
            # платеже и о конце подписки, отключить которые он не просил.
            markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": translate(language, "notify.unsubscribe"),
                            "callback_data": CALLBACK_DATA,
                        }
                    ]
                ]
            }
        await telegram.send_message(recipient, text, markup)

    dispatcher.register(TOPIC_NOTIFY_TELEGRAM, handle_notify_telegram)

    async def handle_support_outbound(payload: dict[str, object]) -> None:
        """Доводит сообщение до темы и держит её название в согласии с состоянием.

        Идентификатор темы записывается своей транзакцией сразу после
        создания: падение на отправке не должно приводить ко второй теме при
        повторе — переписка разорвалась бы надвое.

        Имя правится до закрытия: закрытую тему Bot API переименовывать
        отказывается, и решённое обращение осталось бы красным.
        """
        if support is None:
            msg = "супергруппа поддержки не передана диспетчеру"
            raise RuntimeError(msg)
        ticket_id = int(str(payload["ticket_id"]))
        async with session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if ticket is None:
                # Обращение удалено вместе с аккаунтом: доводить нечего, и
                # сообщение закрывается, а не висит в очереди вечно.
                return
            if ticket.telegram_topic_id is None:
                ticket.telegram_topic_id = await support.create_topic(topic_name(ticket))
                await session.commit()
            topic_id = ticket.telegram_topic_id

            if ticket.topic_status_mark is None:
                counts = (
                    await devices_for_card(session, panel_devices, ticket.user_id)
                    if panel_devices is not None
                    else None
                )
                await support.post(topic_id, await build_card(session, ticket, devices=counts))
                # Отметка ставится вместе с карточкой, а не отдельным шагом:
                # имя новой темы уже собрано с правильной меткой, и без этого
                # проверка ниже переименовала бы её в то же самое.
                ticket.topic_status_mark = ticket.status
                await session.commit()

            body = str(payload.get("body") or "")
            if body:
                await support.post(topic_id, body)

            if ticket.topic_status_mark is not ticket.status:
                await support.rename_topic(topic_id, topic_name(ticket))
                ticket.topic_status_mark = ticket.status
                await session.commit()

            closing = bool(payload.get("close"))
        if closing:
            await support.close_topic(topic_id)

    dispatcher.register(TOPIC_SUPPORT_OUTBOUND, handle_support_outbound)
    return dispatcher
