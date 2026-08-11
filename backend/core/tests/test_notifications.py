"""Категория события решает, куда оно уйдёт."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import NotificationDelivery, OutboxMessage, User
from repibot_core.i18n import has_message
from repibot_core.services.notifications import (
    NotificationCategory,
    NotificationService,
    all_kinds,
    resolve_kind,
)

pytestmark = pytest.mark.docker


async def _user(session: AsyncSession, *, telegram: bool, verified_email: bool) -> User:
    user = User(
        email="both@example.org" if verified_email else None,
        email_verified_at=datetime.now(UTC) if verified_email else None,
        telegram_id=100_501 if telegram else None,
        referral_code="notify01",
    )
    session.add(user)
    await session.flush()
    return user


async def test_service_event_reaches_every_linked_channel(db_session: AsyncSession) -> None:
    """Чек об оплате остаётся человеку письмом, даже если он живёт в Telegram."""
    user = await _user(db_session, telegram=True, verified_email=True)

    staged = await NotificationService(db_session).enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:1:expired:x", params={"plan": "Месяц"}
    )
    await db_session.commit()

    topics = sorted((await db_session.scalars(select(OutboxMessage.topic))).all())
    assert staged == 2
    assert topics == ["notify.email", "notify.telegram"]


async def test_marketing_event_takes_one_channel_preferring_telegram(
    db_session: AsyncSession,
) -> None:
    """Одно и то же предложение дважды — прямой путь к отписке."""
    user = await _user(db_session, telegram=True, verified_email=True)

    await NotificationService(db_session).enqueue(
        user_id=user.id, kind="winback_1", dedup_key="winback:1:step1:x", params={}
    )
    await db_session.commit()

    assert list((await db_session.scalars(select(OutboxMessage.topic))).all()) == [
        "notify.telegram"
    ]


async def test_marketing_event_falls_back_to_verified_email(db_session: AsyncSession) -> None:
    user = await _user(db_session, telegram=False, verified_email=True)

    await NotificationService(db_session).enqueue(
        user_id=user.id, kind="winback_1", dedup_key="winback:2:step1:x", params={}
    )
    await db_session.commit()

    assert list((await db_session.scalars(select(OutboxMessage.topic))).all()) == ["notify.email"]


async def test_no_channel_is_not_an_error(db_session: AsyncSession) -> None:
    """Очередь не должна копить сообщения в никуда."""
    user = await _user(db_session, telegram=False, verified_email=False)

    staged = await NotificationService(db_session).enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:3:expired:x", params={}
    )
    await db_session.commit()

    assert staged == 0
    assert (await db_session.scalars(select(NotificationDelivery))).all() == []


async def test_same_key_is_staged_once(db_session: AsyncSession) -> None:
    user = await _user(db_session, telegram=True, verified_email=False)
    service = NotificationService(db_session)

    first = await service.enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:4:expired:x", params={}
    )
    second = await service.enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:4:expired:x", params={}
    )
    await db_session.commit()

    assert (first, second) == (1, 0)


async def test_opted_out_user_gets_service_but_not_marketing(db_session: AsyncSession) -> None:
    """Отказ от новостей не должен отключать сообщение о потере доступа."""
    user = await _user(db_session, telegram=True, verified_email=False)
    user.marketing_opt_out_at = datetime.now(UTC)
    await db_session.flush()
    service = NotificationService(db_session)

    marketing = await service.enqueue(
        user_id=user.id, kind="winback_1", dedup_key="winback:9:step1:x", params={}
    )
    service_event = await service.enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:9:expired:x", params={}
    )
    await db_session.commit()

    assert (marketing, service_event) == (0, 1)


def test_every_declared_kind_has_texts_in_every_language() -> None:
    """Вид без текстов — это уведомление, падающее у живого человека.

    Реестр видов и словарь переводов лежат в разных файлах, и связь между
    ними держится только на внимательности. Проверка существования ключа, а
    не перевода: параметры у видов разные, и `translate` потребовал бы
    перечислить их все, превратив проверку во второй словарь.
    """
    missing = [
        f"{language}:{kind.text_key}{suffix}"
        for kind in all_kinds()
        for suffix in (".bot", ".subject", ".body")
        for language in ("ru", "en")
        if not has_message(language, f"{kind.text_key}{suffix}")
    ]

    assert missing == []


@pytest.mark.parametrize(
    "kind", ["payment_succeeded", "payment_failed", "auto_renew_failed_1", "auto_renew_failed_3"]
)
def test_money_contour_kinds_are_registered(kind: str) -> None:
    """Реестр обязан знать все виды, которые уже ставит денежный контур.

    Список взят из вызовов enqueue_payment_event в services/payments.py и
    services/payment_notifications.py. Незарегистрированный вид роняет
    финализацию оплаты: деньги списаны, доступ выдан, а процесс падает на
    уведомлении. Ошибка находится не в тестах уведомлений, а в оплате, и
    искать её будут не здесь.
    """
    assert resolve_kind(kind).category is NotificationCategory.service
