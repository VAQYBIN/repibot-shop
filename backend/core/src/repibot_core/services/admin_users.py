"""Люди глазами админки: поиск, карточка, журнал.

Модуль ничего не знает про HTTP: маршруты переводят его ответы в схемы. Так
поиск и склейку журнала можно проверить тестом без токена и роли.

Функции, а не класс: состояния между вызовами нет, а сессия всё равно
приходит каждый раз своя.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from repibot_core.db.models import (
    AuditLog,
    Order,
    Plan,
    Subscription,
    SubscriptionEvent,
    User,
    UserStatus,
)

# Границы знакового 64-битного целого: telegram_id и remnawave_id объявлены
# BigInteger, и строка из тридцати цифр не сравнивается с ними, а роняет
# запрос ошибкой переполнения на стороне Postgres.
_BIGINT_MAX = 2**63 - 1

# Записи журнала действий, относящиеся к человеку. Отбор по сущности
# обязателен: entity_id — строка, и «7» обращения совпало бы с «7» аккаунта.
_USER_AUDIT_ENTITIES = ("user", "subscription")

# Русские названия видов событий подписки: журнал читает человек, а не машина.
_EVENT_TITLES = {
    "trial": "Пробный период",
    "purchase": "Покупка подписки",
    "renew": "Продление",
    "plan_change": "Смена тарифа",
    "bonus_days": "Бонусные дни",
    "gift": "Подарок",
    "expired": "Подписка истекла",
    "admin_grant": "Начисление персоналом",
    "admin_revoke": "Снятие дней персоналом",
    "winback": "Возвращение",
}

_AUDIT_TITLES = {
    "role.granted": "Выдана роль",
    "user.ban": "Блокировка",
    "user.unban": "Разблокировка",
    "user.support_mute": "Поддержка закрыта",
    "user.support_unmute": "Поддержка открыта",
    "user.device_unlink": "Отвязка устройства",
    "user.subscription_link_revoke": "Новая ссылка подписки",
    "subscription.grant": "Правка подписки",
}


@dataclass(frozen=True, slots=True)
class UserRow:
    id: int
    name: str | None
    email: str | None
    telegram_id: int | None
    telegram_username: str | None
    plan_name: str | None
    subscription_status: str | None
    expires_at: datetime | None
    banned: bool
    support_muted: bool


@dataclass(frozen=True, slots=True)
class JournalEntry:
    at: datetime
    kind: str  # subscription | payment | staff
    title: str
    detail: str | None
    actor: str | None  # имя или почта автора; None — система


@dataclass(frozen=True, slots=True)
class UserCard:
    row: UserRow
    language: str
    role: str
    created_at: datetime
    email_verified: bool
    referred_by_id: int | None
    subscription_source: str | None
    auto_renew: bool
    subscription_url: str | None
    remnawave_id: int | None


async def search_users(
    session: AsyncSession, query: str, *, limit: int, offset: int
) -> list[UserRow]:
    """Одна строка поиска на все опознаватели.

    Разбор здесь, а не в интерфейсе: сотрудник не знает, что ему дали —
    почту, ссылку на Telegram или номер, — и разбираться должен сервер.
    """
    statement = _rows_query().order_by(User.id.desc()).limit(limit).offset(offset)
    condition = _condition(query.strip())
    if condition is not None:
        statement = statement.where(condition)
    return [_row(*item) for item in (await session.execute(statement)).all()]


async def user_card(session: AsyncSession, user_id: int) -> UserCard | None:
    """Карточка целиком, кроме устройств: их отдаёт панель, а не база.

    Устройства просит отдельный маршрут — иначе молчащая панель уронила бы
    всю карточку вместе с почтой, тарифом и сроком.
    """
    found = (await session.execute(_rows_query().where(User.id == user_id))).first()
    if found is None:
        return None
    user, subscription, plan_name, plan_code = found
    return UserCard(
        row=_row(user, subscription, plan_name, plan_code),
        language=user.language,
        role=user.role.value,
        created_at=user.created_at,
        email_verified=user.email_verified_at is not None,
        referred_by_id=user.referred_by_id,
        subscription_source=None if subscription is None else subscription.source.value,
        auto_renew=subscription is not None and subscription.auto_renew_enabled,
        subscription_url=user.remnawave_subscription_url,
        remnawave_id=user.remnawave_id,
    )


async def user_journal(session: AsyncSession, user_id: int, *, limit: int) -> list[JournalEntry]:
    """Начисления, деньги и решения персонала одной лентой, свежее сверху.

    Три выборки берут по `limit` каждая, и общий предел режется уже после
    склейки: сто платежей иначе вытеснили бы из ленты все начисления.
    """
    entries = [
        *await _subscription_entries(session, user_id, limit),
        *await _order_entries(session, user_id, limit),
        *await _staff_entries(session, user_id, limit),
    ]
    entries.sort(key=lambda entry: entry.at, reverse=True)
    return entries[:limit]


def _rows_query() -> Select[tuple[User, Subscription, dict[str, str], str]]:
    """Строка списка одним запросом вместе с подпиской и тарифом.

    Отдельный запрос на каждую строку превратил бы страницу из двадцати
    человек в двадцать один запрос. Присоединение внешнее: человек без
    подписки обязан остаться в списке с пустыми полями, а не выпасть из него.

    В подписи подписка и тариф объявлены обязательными, хотя приходят пустыми:
    внешнее присоединение SQLAlchemy в типах не отражает. Пустоту разбирает
    принимающий код — `_row` и `user_card` объявляют её у себя честно.
    """
    return (
        select(User, Subscription, Plan.name, Plan.code)
        .outerjoin(Subscription, Subscription.user_id == User.id)
        .outerjoin(Plan, Plan.id == Subscription.plan_id)
    )


def _condition(query: str) -> ColumnElement[bool] | None:
    """Три правила разбора строки поиска; пустая строка — без отбора."""
    if not query:
        # Список без запроса всё равно нужен: по нему видно, кто пришёл сегодня.
        return None
    if query.isdigit():
        number = int(query)
        if number > _BIGINT_MAX:
            # Столько цифр не бывает ни у одного из наших номеров, а запрос
            # с таким сравнением Postgres отвергает целиком.
            return User.id.is_(None)
        return or_(User.id == number, User.telegram_id == number, User.remnawave_id == number)
    if query.startswith("@"):
        # Вхождением, а не равенством: имя в Telegram сотруднику диктуют вслух
        # и по памяти, и половина его — уже достаточная примета.
        return User.telegram_username.ilike(f"%{_escaped(query[1:])}%")
    return or_(
        User.email.ilike(f"%{_escaped(query)}%"),
        User.name.ilike(f"%{_escaped(query)}%"),
    )


def _escaped(value: str) -> str:
    r"""Экранирует символы шаблона LIKE.

    Почта вида «a_b@example.org» иначе ищется как «a<любой символ>b», и в
    выдачу попадают чужие люди.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row(
    user: User,
    subscription: Subscription | None,
    plan_name: dict[str, str] | None,
    plan_code: str | None,
) -> UserRow:
    return UserRow(
        id=user.id,
        name=user.name,
        email=user.email,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        plan_name=_plan_title(plan_name, plan_code),
        subscription_status=None if subscription is None else subscription.status.value,
        expires_at=None if subscription is None else subscription.expires_at,
        banned=user.status is UserStatus.banned,
        support_muted=user.support_muted_at is not None,
    )


def _plan_title(name: dict[str, str] | None, code: str | None) -> str | None:
    """Название тарифа по-русски: админка живёт без переводов.

    Код на замену — тариф, заведённый без русского названия, иначе показался
    бы пустым местом там, где сотрудник ждёт подписку.
    """
    if name is None:
        return code
    return name.get("ru") or name.get("en") or code


async def _subscription_entries(
    session: AsyncSession, user_id: int, limit: int
) -> list[JournalEntry]:
    actor = aliased(User)
    statement = (
        select(SubscriptionEvent, Plan.name, Plan.code, actor)
        .outerjoin(Plan, Plan.id == SubscriptionEvent.plan_id)
        # Внешнее: автор события мог уволиться, а запись остаётся.
        .outerjoin(actor, actor.id == SubscriptionEvent.actor_user_id)
        .where(SubscriptionEvent.user_id == user_id)
        .order_by(SubscriptionEvent.created_at.desc())
        .limit(limit)
    )
    return [
        JournalEntry(
            at=event.created_at,
            kind="subscription",
            title=_EVENT_TITLES.get(event.type.value, event.type.value),
            detail=_days_detail(event.days_delta, _plan_title(name, code), event.comment),
            actor=_actor_title(author),
        )
        for event, name, code, author in (await session.execute(statement)).all()
    ]


async def _order_entries(session: AsyncSession, user_id: int, limit: int) -> list[JournalEntry]:
    statement = (
        select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(limit)
    )
    return [
        JournalEntry(
            at=order.created_at,
            kind="payment",
            # Заказ называется деньгами: сотрудник ищет в ленте сумму, а не
            # номер строки.
            title=f"Заказ на {order.amount_due_rub} ₽",
            detail=(
                f"{_plan_title(order.plan_name_snapshot, order.plan_code_snapshot)}"
                f" · {order.purpose.value} · {order.status.value}"
            ),
            # Заказ создаёт сам человек: автор персонала здесь означал бы
            # чужое решение, которого не было.
            actor=None,
        )
        for order in (await session.scalars(statement)).all()
    ]


async def _staff_entries(session: AsyncSession, user_id: int, limit: int) -> list[JournalEntry]:
    actor = aliased(User)
    statement = (
        select(AuditLog, actor)
        # Внешнее присоединение и здесь: actor_id гаснет вместе с аккаунтом
        # сотрудника, а запись обязана остаться в ленте.
        .outerjoin(actor, actor.id == AuditLog.actor_id)
        .where(
            AuditLog.entity.in_(_USER_AUDIT_ENTITIES),
            AuditLog.entity_id == str(user_id),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [
        JournalEntry(
            at=record.created_at,
            kind="staff",
            title=_AUDIT_TITLES.get(record.action, record.action),
            detail=_state_detail(record.before, record.after),
            actor=_actor_title(author),
        )
        for record, author in (await session.execute(statement)).all()
    ]


def _actor_title(actor: User | None) -> str | None:
    """Имя, почта или номер: подпись должна остаться даже у безымянного."""
    if actor is None:
        return None
    return actor.name or actor.email or f"#{actor.id}"


def _days_detail(days: int, plan: str | None, comment: str | None) -> str | None:
    parts = [f"{days:+d} дн."]
    if plan is not None:
        parts.append(plan)
    if comment:
        parts.append(comment)
    return " · ".join(parts)


def _state_detail(before: dict[str, Any] | None, after: dict[str, Any] | None) -> str | None:
    """Состояние до и после — то, ради чего журнал и ведётся.

    Снимок показывается словами из самой записи: сервисы кладут туда «active»
    и «banned», и переводить их здесь значило бы держать словарь всех действий
    персонала сразу в двух местах.
    """
    left = _state(before)
    right = _state(after)
    if left is None and right is None:
        return None
    if left is None:
        return right
    return f"{left} → {right}"


def _state(snapshot: dict[str, Any] | None) -> str | None:
    if not snapshot:
        return None
    return ", ".join(f"{key}: {value}" for key, value in snapshot.items())
