"""Сборка диспетчера очереди со всеми известными темами.

Отдельный модуль, потому что тем стало больше одной группы: почта не должна
знать про панель, а панель — про почту.
"""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.i18n import translate
from repibot_core.integrations.email.sender import EmailSender
from repibot_core.integrations.remnawave.client import create_remnawave_client
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.integrations.telegram.bot_api import BotApi
from repibot_core.services.email_dispatch import build_dispatcher as build_email_dispatcher
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.services.payment_notifications import TOPIC_PAYMENT_TELEGRAM
from repibot_core.services.provisioning import TOPIC_PROVISION, build_provision_handler
from repibot_core.settings import get_settings


def build_dispatcher(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    sender: EmailSender | None = None,
    users: PanelUsers | None = None,
    telegram: BotApi | None = None,
) -> OutboxDispatcher:
    """Диспетчер со всеми темами этапа.

    Отправитель и фасад панели принимаются параметрами, чтобы тест подставил
    свои, не трогая настройки окружения.
    """
    dispatcher = build_email_dispatcher(sender)
    panel = users if users is not None else PanelUsers(create_remnawave_client())
    dispatcher.register(TOPIC_PROVISION, build_provision_handler(session_factory, panel))

    async def handle_payment_telegram(payload: dict[str, object]) -> None:
        language = str(payload["language"])
        kind = str(payload["kind"])
        plan = str(payload["plan"])
        prefix = "payment.succeeded" if kind == "payment_succeeded" else "payment.failed"
        text = translate(language, f"{prefix}.bot", plan=plan)
        recipient = int(str(payload["recipient"]))
        if telegram is not None:
            await telegram.send_message(recipient, text)
            return
        settings = get_settings()
        redis = Redis.from_url(settings.valkey_url)
        bot = BotApi(settings, redis)
        try:
            await bot.send_message(recipient, text)
        finally:
            await bot.aclose()
            await redis.aclose()

    dispatcher.register(TOPIC_PAYMENT_TELEGRAM, handle_payment_telegram)
    return dispatcher
