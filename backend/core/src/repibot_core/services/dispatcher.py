"""Сборка диспетчера очереди со всеми известными темами.

Отдельный модуль, потому что тем стало больше одной группы: почта не должна
знать про панель, а панель — про почту.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.integrations.email.sender import EmailSender
from repibot_core.integrations.remnawave.client import create_remnawave_client
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.email_dispatch import build_dispatcher as build_email_dispatcher
from repibot_core.services.outbox import OutboxDispatcher
from repibot_core.services.provisioning import TOPIC_PROVISION, build_provision_handler


def build_dispatcher(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    sender: EmailSender | None = None,
    users: PanelUsers | None = None,
) -> OutboxDispatcher:
    """Диспетчер со всеми темами этапа.

    Отправитель и фасад панели принимаются параметрами, чтобы тест подставил
    свои, не трогая настройки окружения.
    """
    dispatcher = build_email_dispatcher(sender)
    panel = users if users is not None else PanelUsers(create_remnawave_client())
    dispatcher.register(TOPIC_PROVISION, build_provision_handler(session_factory, panel))
    return dispatcher
