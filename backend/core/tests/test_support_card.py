"""Карточка собеседника: всё, что помогает решить вопрос, одним сообщением."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Plan,
    Subscription,
    SubscriptionSource,
    Ticket,
    TicketStatus,
    User,
    UserStatus,
)
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.support_card import build_card, devices_for_card

pytestmark = pytest.mark.docker


async def _plan(session: AsyncSession, code: str) -> Plan:
    plan = Plan(
        code=code,
        name={"ru": "Год", "en": "Year"},
        description=None,
        duration_days=365,
        price_rub=Decimal("1990.00"),
        price_stars=1990,
        hwid_device_limit=5,
        internal_squad_uuids=[],
    )
    session.add(plan)
    await session.flush()
    return plan


async def _user(session: AsyncSession, code: str, **fields: Any) -> User:
    user = User(referral_code=code, **fields)
    session.add(user)
    await session.flush()
    return user


async def _ticket(session: AsyncSession, user: User) -> Ticket:
    ticket = Ticket(user_id=user.id, status=TicketStatus.waiting_staff, subject="Не открывается")
    session.add(ticket)
    await session.flush()
    return ticket


async def _subscribe(
    session: AsyncSession, user: User, plan: Plan, *, expires_in: int, auto_renew: bool = True
) -> None:
    session.add(
        Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionState.active,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=expires_in),
            auto_renew_enabled=auto_renew,
            source=SubscriptionSource.purchase,
        )
    )
    await session.flush()


async def test_card_names_the_person_and_their_subscription(db_session: AsyncSession) -> None:
    """Сотрудник должен узнать собеседника, не открывая админку."""
    user = await _user(
        db_session,
        "card0001",
        email="ivan@example.com",
        email_verified_at=datetime.now(UTC),
        telegram_id=513_442_219,
        telegram_username="ivan",
        name="Иван",
    )
    plan = await _plan(db_session, "card-year")
    await _subscribe(db_session, user, plan, expires_in=83)
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=(3, 5))

    assert "Иван" in card
    assert f"#{ticket.id}" in card
    assert "@ivan" in card
    assert "513442219" in card
    assert "ivan@example.com" in card
    assert "Год" in card
    assert "83" in card
    assert "3 из 5" in card
    assert "/close_silent" in card


async def test_person_without_telegram_is_named_as_such(db_session: AsyncSession) -> None:
    """Половина плательщиков пришла почтой: без этой строки сотрудник ищет
    несуществующий аккаунт в Telegram."""
    user = await _user(db_session, "card0002", email="mail@example.com")
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "Telegram: не привязан" in card
    assert "Без имени" in card


async def test_telegram_without_username_leaves_the_number(db_session: AsyncSession) -> None:
    """По числу сотрудник хотя бы найдёт человека в админке; @ у него нет."""
    user = await _user(db_session, "card0003", email=None, telegram_id=513_000_003)
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "Telegram: 513000003" in card
    assert "@" not in card


async def test_missing_email_leaves_no_empty_line(db_session: AsyncSession) -> None:
    """Пустая строка «Почта: —» отнимает место и ничего не сообщает."""
    user = await _user(db_session, "card0004", email=None, telegram_id=513_000_004)
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "Почта" not in card


async def test_unconfirmed_email_is_marked(db_session: AsyncSession) -> None:
    """Письма такому человеку не доходят — а поддержка как раз ими и отвечает."""
    user = await _user(db_session, "card0005", email="cold@example.com")
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "не подтверждена" in card


async def test_person_without_a_subscription_is_named_as_such(db_session: AsyncSession) -> None:
    """Вопрос «почему не работает» у не купившего решается иначе, чем у купившего."""
    user = await _user(db_session, "card0006", email=None, telegram_id=513_000_006)
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "Подписка: не покупал" in card


async def test_expired_subscription_says_how_long_ago(db_session: AsyncSession) -> None:
    """Самая частая причина «перестало работать» — подписка кончилась вчера."""
    user = await _user(db_session, "card0007", email=None, telegram_id=513_000_007)
    plan = await _plan(db_session, "card-old")
    await _subscribe(db_session, user, plan, expires_in=-14)
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "истекла" in card
    assert "14 дн. назад" in card


async def test_silent_autorenew_is_still_shown(db_session: AsyncSession) -> None:
    """Спор «почему с меня списали» начинается с этой строки."""
    user = await _user(db_session, "card0008", email=None, telegram_id=513_000_008)
    plan = await _plan(db_session, "card-manual")
    await _subscribe(db_session, user, plan, expires_in=5, auto_renew=False)
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "Автопродление: выключено" in card


async def test_unknown_device_count_is_not_a_zero(db_session: AsyncSession) -> None:
    """Ноль устройств и молчание панели — разные новости: по первой сотрудник
    сказал бы «вы ничего не подключили», а это неправда."""
    user = await _user(db_session, "card0009", email=None, telegram_id=513_000_009)
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "Устройства: н/д" in card


async def test_blocked_person_is_marked(db_session: AsyncSession) -> None:
    """Иначе непонятно, почему собеседник перестал отвечать."""
    user = await _user(
        db_session, "card0010", email=None, telegram_id=513_000_010, status=UserStatus.banned
    )
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "⛔ Заблокирован" in card


async def test_muted_person_is_marked(db_session: AsyncSession) -> None:
    """Заглушённый не может ответить в это же обращение — сотруднику лучше
    узнать об этом до того, как он задаст уточняющий вопрос."""
    user = await _user(
        db_session,
        "card0011",
        email=None,
        telegram_id=513_000_011,
        support_muted_at=datetime.now(UTC),
    )
    ticket = await _ticket(db_session, user)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=None)

    assert "🔇 Поддержка закрыта" in card


class _Panel:
    """Панель, у которой два устройства."""

    async def list(self, panel_id: int) -> list[object]:
        return [object(), object()]


class _DeadPanel:
    """Панель, которая не отвечает. Карточка обязана пережить её молчание."""

    async def list(self, panel_id: int) -> list[object]:
        msg = "панель недоступна"
        raise RuntimeError(msg)


async def test_devices_are_counted_by_the_panel_against_the_plan_limit(
    db_session: AsyncSession,
) -> None:
    """Лимит тарифа без реального числа не отвечает на «почему не подключается
    ещё одно устройство» — самый частый вопрос в поддержке."""
    user = await _user(db_session, "card0012", email=None, telegram_id=513_000_012, remnawave_id=77)
    plan = await _plan(db_session, "card-devices")
    await _subscribe(db_session, user, plan, expires_in=30)
    await db_session.commit()

    counts = await devices_for_card(db_session, _Panel(), user.id)  # type: ignore[arg-type]

    assert counts == (2, 5)


async def test_dead_panel_leaves_the_card_without_devices(db_session: AsyncSession) -> None:
    """Отказ панели не должен мешать создать тему: обращение важнее строки."""
    user = await _user(db_session, "card0013", email=None, telegram_id=513_000_013, remnawave_id=78)
    plan = await _plan(db_session, "card-dead")
    await _subscribe(db_session, user, plan, expires_in=30)
    await db_session.commit()

    assert await devices_for_card(db_session, _DeadPanel(), user.id) is None  # type: ignore[arg-type]


async def test_person_outside_the_panel_has_nothing_to_count(db_session: AsyncSession) -> None:
    """Не заведённого в панели спрашивать не о чем, и лишний запрос ей ни к чему."""
    user = await _user(db_session, "card0014", email=None, telegram_id=513_000_014)
    await db_session.commit()

    assert await devices_for_card(db_session, _DeadPanel(), user.id) is None  # type: ignore[arg-type]
