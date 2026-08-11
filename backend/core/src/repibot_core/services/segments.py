"""Именованные сегменты аудитории.

Именованные, а не конструктор условий: конструктор — это отдельный язык
запросов со своими багами, и опечатка в нём отправляет письмо всей базе.
Каждый сегмент здесь покрыт своим тестом.
"""

from __future__ import annotations

from sqlalchemy import Select, String, case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Order, OrderStatus, Plan, Subscription, User, UserStatus
from repibot_core.domain.subscriptions import SubscriptionState

SEGMENTS: dict[str, str] = {
    "all": "Все",
    "active": "С активной подпиской",
    "expired": "Истёкшие",
    "never_paid": "Ни разу не платившие",
    "trial": "На триале",
}

# Префикс сегмента по тарифу: `plan:month`. Отдельная форма, потому что имён
# тарифов заранее не знает никто.
PLAN_PREFIX = "plan:"


def _base() -> Select[tuple[int, str, str, str]]:
    """Пользователи с действующим каналом, кроме отписавшихся.

    Канал выбирается по тому же правилу, что и у маркетинговых уведомлений:
    Telegram приоритетнее подтверждённой почты. Правило записано выражением
    базы, а не циклом в Python: аудитория материализуется одним запросом.

    Фильтр стоит здесь, а не только в предпросмотре охвата: отписавшийся между
    черновиком и запуском иначе всё равно получил бы письмо.
    """
    channel = case((User.telegram_id.is_not(None), "telegram"), else_="email").label("channel")
    recipient = case(
        (User.telegram_id.is_not(None), User.telegram_id.cast(String)), else_=User.email
    ).label("recipient")
    # Колонки именованные: материализация получателей обращается к ним по
    # имени подзапроса, и порядковый доступ сломался бы от любой перестановки.
    return select(
        User.id.label("user_id"), channel, recipient, User.language.label("language")
    ).where(
        User.marketing_opt_out_at.is_(None),
        # Заблокированному нечего предлагать: доступа у него нет и не будет,
        # пока блокировка держится, а отписываться он не отписывался — без
        # этого условия он попал бы в каждую рассылку.
        User.status == UserStatus.active,
        User.telegram_id.is_not(None)
        | (User.email.is_not(None) & User.email_verified_at.is_not(None)),
    )


def segment_query(name: str) -> Select[tuple[int, str, str, str]]:
    """Запрос сегмента по имени. Неизвестное имя — ошибка, а не пустая выборка."""
    if name.startswith(PLAN_PREFIX):
        code = name[len(PLAN_PREFIX) :]
        return _base().where(
            exists(
                select(Subscription.id)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(
                    Subscription.user_id == User.id,
                    Subscription.status == SubscriptionState.active,
                    Plan.code == code,
                )
            )
        )
    if name == "all":
        return _base()
    if name == "active":
        return _base().where(
            exists(
                select(Subscription.id).where(
                    Subscription.user_id == User.id,
                    Subscription.status == SubscriptionState.active,
                )
            )
        )
    if name == "expired":
        return _base().where(
            exists(
                select(Subscription.id).where(
                    Subscription.user_id == User.id,
                    Subscription.status == SubscriptionState.expired,
                )
            )
        )
    if name == "trial":
        return _base().where(
            exists(
                select(Subscription.id)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(
                    Subscription.user_id == User.id,
                    Subscription.status == SubscriptionState.active,
                    Plan.is_trial.is_(True),
                )
            )
        )
    if name == "never_paid":
        return _base().where(
            ~exists(
                select(Order.id).where(
                    Order.user_id == User.id, Order.status == OrderStatus.fulfilled
                )
            )
        )
    msg = f"неизвестный сегмент: {name}"
    raise KeyError(msg)


async def count_segment(session: AsyncSession, name: str) -> int:
    """Охват до запуска. Меняется вместе с базой — это и есть его смысл.

    Считает база, а не Python: перед запуском на пять тысяч человек тянуть
    все строки в память ради одного числа незачем.
    """
    counted = await session.scalar(select(func.count()).select_from(segment_query(name).subquery()))
    return int(counted or 0)
