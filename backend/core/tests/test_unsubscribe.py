"""Отписка без входа: ссылка в письме и кнопка в Telegram."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from repibot_core.db.engine import create_session_factory
from repibot_core.db.models import User
from repibot_core.integrations.email.sender import LoggingEmailSender
from repibot_core.integrations.telegram.bot_api import BotApi
from repibot_core.security.tokens import create_access_token
from repibot_core.services.dispatcher import build_dispatcher
from repibot_core.services.email_dispatch import build_dispatcher as build_email_dispatcher
from repibot_core.services.errors import ServiceError
from repibot_core.services.notifications import NotificationService
from repibot_core.services.unsubscribe import UnsubscribeService, sign_unsubscribe_token
from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker


async def _user(session: AsyncSession, *, telegram: bool = False, email: bool = False) -> User:
    user = User(
        email="unsub@example.org" if email else None,
        email_verified_at=datetime.now(UTC) if email else None,
        telegram_id=100_601 if telegram else None,
        referral_code="unsub001",
    )
    session.add(user)
    await session.flush()
    return user


def _capturing_bot(sent: list[dict[str, Any]]) -> BotApi:
    """Настоящий BotApi поверх подставного транспорта.

    Заглушка вместо класса проверяла бы саму себя: тело запроса к Bot API
    собирает именно `send_message`, и кнопка обязана оказаться в нём.
    """

    async def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return BotApi(get_settings(), FakeRedis(), client=client)


async def test_token_switches_marketing_off(db_session: AsyncSession) -> None:
    user = await _user(db_session, telegram=True)

    await UnsubscribeService(db_session).apply(sign_unsubscribe_token(user.id))
    await db_session.commit()

    assert user.marketing_opt_out_at is not None


async def test_foreign_signature_is_rejected(db_session: AsyncSession) -> None:
    """Токен подписан нашим секретом: подделка не должна отписывать чужого."""
    with pytest.raises(ServiceError) as failure:
        await UnsubscribeService(db_session).apply("не.наш.токен")

    assert failure.value.code == "invalid_token"


async def test_access_token_is_not_an_unsubscribe_link(db_session: AsyncSession) -> None:
    """Access-токен подписан тем же секретом и обязан быть отвергнут.

    Без проверки назначения любой перехваченный или просто подсмотренный
    access-токен отписывал бы своего владельца от всего маркетинга.
    """
    user = await _user(db_session, telegram=True)
    access = create_access_token(
        user.id,
        uuid4(),
        secret=get_settings().jwt_secret.get_secret_value(),
        ttl_minutes=15,
    )

    with pytest.raises(ServiceError) as failure:
        await UnsubscribeService(db_session).apply(access)

    assert failure.value.code == "invalid_token"
    assert user.marketing_opt_out_at is None


async def test_token_of_a_deleted_user_is_rejected(db_session: AsyncSession) -> None:
    """Ссылка из старого письма не должна ронять маршрут после удаления аккаунта."""
    with pytest.raises(ServiceError) as failure:
        await UnsubscribeService(db_session).apply(sign_unsubscribe_token(999_999))

    assert failure.value.code == "invalid_token"


async def test_marketing_telegram_message_carries_an_unsubscribe_button(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Отписка обязана быть на расстоянии касания, иначе человек блокирует бота."""
    user = await _user(db_session, telegram=True)
    await NotificationService(db_session).enqueue(
        user_id=user.id, kind="winback_1", dedup_key="winback:1:step1:x", params={}
    )
    await db_session.commit()
    sent: list[dict[str, Any]] = []

    await build_dispatcher(
        create_session_factory(engine), sender=LoggingEmailSender(), telegram=_capturing_bot(sent)
    ).process(db_session)

    assert sent[0]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "unsub"


async def test_service_telegram_message_has_no_button(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Отписаться от сообщения о потере доступа нельзя: предлагать нечего."""
    user = await _user(db_session, telegram=True)
    await NotificationService(db_session).enqueue(
        user_id=user.id,
        kind="expired",
        dedup_key="sub:1:expired:x",
        params={"plan": "Месяц", "date": "01.01.2027"},
    )
    await db_session.commit()
    sent: list[dict[str, Any]] = []

    await build_dispatcher(
        create_session_factory(engine), sender=LoggingEmailSender(), telegram=_capturing_bot(sent)
    ).process(db_session)

    assert "reply_markup" not in sent[0]


async def test_marketing_letter_carries_an_unsubscribe_link(db_session: AsyncSession) -> None:
    """Письмо без ссылки отписки уезжает в спам вместе со всей нашей почтой."""
    user = await _user(db_session, email=True)
    await NotificationService(db_session).enqueue(
        user_id=user.id, kind="winback_1", dedup_key="winback:2:step1:x", params={}
    )
    await db_session.commit()
    sender = LoggingEmailSender()

    await build_email_dispatcher(sender).process(db_session)

    assert "/unsubscribe?token=" in sender.sent[0].text
    assert sender.sent[0].text.count("/unsubscribe?token=") == 1


async def test_service_letter_has_no_unsubscribe_link(db_session: AsyncSession) -> None:
    user = await _user(db_session, email=True)
    await NotificationService(db_session).enqueue(
        user_id=user.id,
        kind="expired",
        dedup_key="sub:2:expired:x",
        params={"plan": "Месяц", "date": "01.01.2027"},
    )
    await db_session.commit()
    sender = LoggingEmailSender()

    await build_email_dispatcher(sender).process(db_session)

    assert "/unsubscribe?token=" not in sender.sent[0].text
