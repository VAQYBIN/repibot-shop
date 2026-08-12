"""Поиск людей, карточка и журнал для админки."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    AuditLog,
    Order,
    OrderPurpose,
    OrderStatus,
    Plan,
    Subscription,
    SubscriptionActor,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionSource,
    User,
    UserRole,
    UserStatus,
)
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.admin_users import search_users, user_card, user_journal

pytestmark = pytest.mark.docker

# Номер, которого в базе заведомо нет: схема пересоздаётся на каждый тест, и
# последовательность идентификаторов никогда не доходит до миллиона.
MISSING_USER_ID = 1_000_000

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


async def _user(session: AsyncSession, code: str, **fields: object) -> User:
    """Аккаунт без способов входа: поиску важны опознаватели, а не вход."""
    user = User(referral_code=code, **fields)
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def _plan(session: AsyncSession, code: str, title: str) -> Plan:
    plan = Plan(
        code=code,
        name={"ru": title, "en": code},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        internal_squad_uuids=[],
    )
    session.add(plan)
    await session.flush()
    await session.commit()
    return plan


async def _subscription(
    session: AsyncSession, user: User, plan: Plan, **fields: object
) -> Subscription:
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=29),
        source=SubscriptionSource.purchase,
        **fields,
    )
    session.add(subscription)
    await session.flush()
    await session.commit()
    return subscription


async def _order(session: AsyncSession, user: User, plan: Plan, *, at: datetime) -> Order:
    order = Order(
        user_id=user.id,
        purpose=OrderPurpose.purchase,
        plan_id=plan.id,
        plan_code_snapshot=plan.code,
        plan_name_snapshot=plan.name,
        duration_days_snapshot=30,
        price_rub_snapshot=Decimal("299.00"),
        price_stars_snapshot=199,
        gross_rub=Decimal("299.00"),
        discount_rub=Decimal("0.00"),
        amount_due_rub=Decimal("299.00"),
        client_key=f"key-{user.id}-{at.isoformat()}",
        expires_at=at + timedelta(hours=1),
        status=OrderStatus.fulfilled,
        created_at=at,
    )
    session.add(order)
    await session.flush()
    await session.commit()
    return order


async def _event(
    session: AsyncSession, user: User, plan: Plan, *, at: datetime, actor: User | None = None
) -> SubscriptionEvent:
    event = SubscriptionEvent(
        user_id=user.id,
        type=SubscriptionEventType.purchase,
        days_delta=30,
        plan_id=plan.id,
        actor=SubscriptionActor.user if actor is None else SubscriptionActor.admin,
        actor_user_id=None if actor is None else actor.id,
        comment=None,
        created_at=at,
    )
    session.add(event)
    await session.flush()
    await session.commit()
    return event


async def _audit(
    session: AsyncSession, user: User, *, at: datetime, actor: User | None = None
) -> AuditLog:
    record = AuditLog(
        actor_id=None if actor is None else actor.id,
        action="user.ban",
        entity="user",
        entity_id=str(user.id),
        before={"state": "active"},
        after={"state": "banned"},
        created_at=at,
    )
    session.add(record)
    await session.flush()
    await session.commit()
    return record


# --- поиск ---


async def test_digits_match_every_numeric_identifier(db_session: AsyncSession) -> None:
    """Гадать по длине нельзя: номер в панели растёт с каждым заведённым
    пользователем и однажды сравняется по длине с номером аккаунта."""
    by_account = await _user(db_session, "search01", telegram_id=700_001, remnawave_id=42)
    by_panel = await _user(db_session, "search02", telegram_id=700_002, remnawave_id=700_001)

    found = await search_users(db_session, "700001", limit=20, offset=0)

    assert {row.id for row in found} == {by_account.id, by_panel.id}


async def test_digits_match_the_account_number_too(db_session: AsyncSession) -> None:
    """Номер аккаунта — тот самый, который сотрудник видит в адресе карточки."""
    person = await _user(db_session, "search03")

    found = await search_users(db_session, str(person.id), limit=20, offset=0)

    assert [row.id for row in found] == [person.id]


async def test_a_number_longer_than_any_identifier_finds_nobody(db_session: AsyncSession) -> None:
    """Тридцать цифр — не номер, а опечатка: запрос обязан вернуть пустоту,
    а не упасть переполнением на стороне Postgres."""
    await _user(db_session, "search04", telegram_id=700_003)

    assert await search_users(db_session, "9" * 30, limit=20, offset=0) == []


async def test_at_sign_searches_the_telegram_handle(db_session: AsyncSession) -> None:
    """Ссылку на человека сотруднику присылают именно так: @имя."""
    wanted = await _user(db_session, "search05", telegram_username="Pavel_R")
    await _user(db_session, "search06", telegram_username="someone")

    found = await search_users(db_session, "@pavel", limit=20, offset=0)

    assert [row.id for row in found] == [wanted.id]


async def test_words_search_email_and_name_by_substring(db_session: AsyncSession) -> None:
    """Человек помнит кусок почты или имени, а не строку целиком.

    Регистр не различается: почту диктуют как придётся, а имя человек писал
    себе сам.
    """
    by_email = await _user(db_session, "search07", email="pavel@example.org")
    by_name = await _user(db_session, "search08", name="Pavel Иванов")
    await _user(db_session, "search09", email="other@example.org", name="Кто-то")

    found = await search_users(db_session, "PaVeL", limit=20, offset=0)

    assert {row.id for row in found} == {by_email.id, by_name.id}


async def test_underscore_in_a_query_is_not_a_wildcard(db_session: AsyncSession) -> None:
    """Подчёркивание в шаблоне LIKE значит «любой символ»: без экранирования
    поиск по «a_b» выдал бы сотруднику чужие аккаунты."""
    await _user(db_session, "search10", email="axb@example.org")

    assert await search_users(db_session, "a_b", limit=20, offset=0) == []


async def test_empty_query_lists_the_freshest_first(db_session: AsyncSession) -> None:
    """Список без строки поиска нужен, чтобы увидеть пришедших сегодня."""
    first = await _user(db_session, "search11")
    second = await _user(db_session, "search12")

    found = await search_users(db_session, "   ", limit=20, offset=0)

    assert [row.id for row in found] == [second.id, first.id]


async def test_offset_and_limit_page_the_list(db_session: AsyncSession) -> None:
    """Страница выдачи — двадцать строк, дальше кнопка «ещё» со смещением."""
    first = await _user(db_session, "search13")
    await _user(db_session, "search14")

    found = await search_users(db_session, "", limit=1, offset=1)

    assert [row.id for row in found] == [first.id]


async def test_a_person_without_a_subscription_still_has_a_row(db_session: AsyncSession) -> None:
    """Не купивший — тоже человек в поиске: у него пустой тариф, а не пустая
    выдача. Иначе сотрудник решил бы, что аккаунта нет вовсе."""
    person = await _user(db_session, "search15", email="nobody@example.org")

    found = await search_users(db_session, "nobody", limit=20, offset=0)

    assert [row.id for row in found] == [person.id]
    assert found[0].plan_name is None
    assert found[0].subscription_status is None
    assert found[0].expires_at is None


async def test_row_carries_the_plan_and_the_restrictions(db_session: AsyncSession) -> None:
    """Отметки ⛔ и 🔇 рисуются по строке списка: заходить в карточку ради
    вопроса «почему он молчит» сотрудник не должен."""
    plan = await _plan(db_session, "month", "Месяц")
    person = await _user(
        db_session,
        "search16",
        email="banned@example.org",
        status=UserStatus.banned,
        support_muted_at=NOW,
    )
    await _subscription(db_session, person, plan)

    found = await search_users(db_session, "banned@example.org", limit=20, offset=0)

    assert [row.plan_name for row in found] == ["Месяц"]
    assert found[0].subscription_status == "active"
    assert found[0].expires_at is not None
    assert (found[0].banned, found[0].support_muted) == (True, True)


# --- карточка ---


async def test_card_shows_who_this_is(db_session: AsyncSession) -> None:
    """Половина обращений решается тем, что сотрудник видит человека целиком."""
    plan = await _plan(db_session, "month", "Месяц")
    inviter = await _user(db_session, "card0001")
    person = await _user(
        db_session,
        "card0002",
        email="person@example.org",
        email_verified_at=NOW,
        telegram_id=800_001,
        telegram_username="person",
        name="Павел",
        language="en",
        role=UserRole.support,
        referred_by_id=inviter.id,
        remnawave_id=77,
        remnawave_subscription_url="https://panel.example.org/sub/abc",
    )
    await _subscription(db_session, person, plan, auto_renew_enabled=True)

    card = await user_card(db_session, person.id)

    assert card is not None
    assert card.row.email == "person@example.org"
    assert card.row.plan_name == "Месяц"
    assert (card.language, card.role) == ("en", "support")
    assert card.email_verified is True
    assert card.referred_by_id == inviter.id
    assert card.subscription_source == "purchase"
    assert card.auto_renew is True
    assert card.subscription_url == "https://panel.example.org/sub/abc"
    assert card.remnawave_id == 77
    assert card.created_at is not None


async def test_card_opens_without_a_subscription(db_session: AsyncSession) -> None:
    """Не купивший обращается в поддержку чаще купившего: его карточка обязана
    открываться, а не отвечать «подписки нет»."""
    person = await _user(db_session, "card0003", email="fresh@example.org")

    card = await user_card(db_session, person.id)

    assert card is not None
    assert card.row.subscription_status is None
    assert card.subscription_source is None
    assert card.auto_renew is False
    assert card.subscription_url is None


async def test_card_opens_without_telegram(db_session: AsyncSession) -> None:
    """Вошедший почтой Telegram не привязывал, и это не повод терять карточку."""
    person = await _user(db_session, "card0004", email="mail-only@example.org")

    card = await user_card(db_session, person.id)

    assert card is not None
    assert (card.row.telegram_id, card.row.telegram_username) == (None, None)
    assert card.email_verified is False


async def test_card_of_an_unknown_number_is_empty(db_session: AsyncSession) -> None:
    """Номер из чужой вкладки не должен превращаться в поломку."""
    assert await user_card(db_session, MISSING_USER_ID) is None


# --- журнал ---


async def test_journal_merges_three_sources_by_time(db_session: AsyncSession) -> None:
    """Начисление, оплата и решение персонала — одна история одного человека.
    Порядок обратный: разбирают всегда последнее, а не первое."""
    plan = await _plan(db_session, "month", "Месяц")
    staff = await _user(db_session, "jour0001", name="Дежурный", role=UserRole.support)
    person = await _user(db_session, "jour0002")
    await _event(db_session, person, plan, at=NOW - timedelta(hours=3))
    await _order(db_session, person, plan, at=NOW - timedelta(hours=2))
    await _audit(db_session, person, at=NOW - timedelta(hours=1), actor=staff)

    entries = await user_journal(db_session, person.id, limit=20)

    assert [entry.kind for entry in entries] == ["staff", "payment", "subscription"]
    assert entries[0].actor == "Дежурный"
    assert entries[0].title == "Блокировка"
    assert entries[1].title == "Заказ на 299.00 ₽"
    assert entries[2].title == "Покупка подписки"
    assert entries[2].detail is not None and "+30 дн." in entries[2].detail


async def test_journal_survives_a_deleted_actor(db_session: AsyncSession) -> None:
    """`audit_log.actor_id` гаснет вместе с аккаунтом сотрудника, а запись
    остаётся: журнал не должен терять строку из-за уволенного коллеги."""
    staff = await _user(db_session, "jour0003", name="Уволенный", role=UserRole.support)
    person = await _user(db_session, "jour0004")
    await _audit(db_session, person, at=NOW - timedelta(hours=1), actor=staff)

    await db_session.delete(staff)
    await db_session.commit()

    entries = await user_journal(db_session, person.id, limit=20)

    assert [entry.kind for entry in entries] == ["staff"]
    assert entries[0].actor is None
    assert entries[0].detail == "state: active → state: banned"


async def test_journal_holds_events_of_a_person_only(db_session: AsyncSession) -> None:
    """Запись журнала адресует человека строкой: без отбора по сущности
    обращение №7 попало бы в ленту аккаунта №7."""
    person = await _user(db_session, "jour0005")
    stranger = await _user(db_session, "jour0006")
    await _audit(db_session, stranger, at=NOW - timedelta(hours=1))
    db_session.add(
        AuditLog(
            actor_id=None,
            action="ticket.close",
            entity="ticket",
            entity_id=str(person.id),
            before=None,
            after=None,
            created_at=NOW,
        )
    )
    await db_session.commit()

    assert await user_journal(db_session, person.id, limit=20) == []


async def test_journal_limit_does_not_let_one_source_crowd_out_others(
    db_session: AsyncSession,
) -> None:
    """Предел берётся с запасом на каждую ленту и режется после склейки: сто
    платежей иначе вытеснили бы из журнала все начисления."""
    plan = await _plan(db_session, "month", "Месяц")
    person = await _user(db_session, "jour0007")
    for hour in range(5):
        await _order(db_session, person, plan, at=NOW - timedelta(hours=10 + hour))
    await _event(db_session, person, plan, at=NOW - timedelta(hours=1))

    entries = await user_journal(db_session, person.id, limit=3)

    assert len(entries) == 3
    assert entries[0].kind == "subscription"
