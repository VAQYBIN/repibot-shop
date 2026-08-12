"""Карточка собеседника для темы поддержки.

Модуль ничего не знает про Telegram и отдаёт готовый текст: так его можно
проверить тестом без супергруппы, а звать — и из разбора очереди, и из
команды `/info`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Plan, Subscription, Ticket, User, UserStatus
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.integrations.remnawave.devices import PanelDevices

logger = logging.getLogger(__name__)

# Команды перечислены в самой карточке: рабочий чат — единственное место, где
# сотрудник о них узнаёт, а справки в интерфейсе у него нет.
COMMANDS = "Команды: /info /close /close_silent /mute /unmute /ban /unban"

DATE_FORMAT = "%d.%m.%Y"


async def build_card(
    session: AsyncSession, ticket: Ticket, *, devices: tuple[int, int] | None
) -> str:
    """Текст карточки. Отсутствующие сведения не показываются пустыми строками."""
    user = await UserRepository(session).get(ticket.user_id)
    if user is None:
        # Обращение живёт только вместе с аккаунтом, но разбор очереди может
        # застать удаление: карточка без собеседника лучше упавшей задачи.
        return f"👤 Аккаунт удалён · обращение #{ticket.id}\n\n{COMMANDS}"

    lines = [_head(user, ticket), _telegram(user)]
    email = _email(user)
    if email is not None:
        lines.append(email)
    subscription = await SubscriptionRepository(session).get_for_user(user.id)
    plan = (
        await PlanRepository(session).get(subscription.plan_id)
        if subscription is not None
        else None
    )
    lines.extend(_subscription(subscription, plan))
    lines.append(_devices(devices))
    lines.append(f"С нами с {user.created_at.strftime(DATE_FORMAT)}")
    lines.extend(_restrictions(user))
    return "\n".join(lines) + f"\n\n{COMMANDS}"


async def devices_for_card(
    session: AsyncSession, panel: PanelDevices, user_id: int
) -> tuple[int, int] | None:
    """Привязанные устройства и лимит тарифа.

    Отказ панели гасится здесь: карточка без числа устройств хуже карточки с
    ним, но несозданная тема хуже обеих.
    """
    user = await UserRepository(session).get(user_id)
    if user is None or user.remnawave_id is None:
        return None
    subscription = await SubscriptionRepository(session).get_for_user(user_id)
    if subscription is None:
        return None
    plan = await PlanRepository(session).get(subscription.plan_id)
    try:
        found = await panel.list(user.remnawave_id)
    except Exception:  # отказ панели любой природы не должен рвать создание темы
        logger.warning("панель не ответила об устройствах", exc_info=True, extra={"user": user_id})
        return None
    return len(found), plan.hwid_device_limit if plan is not None else 0


def _head(user: User, ticket: Ticket) -> str:
    name = user.name or "Без имени"
    return f"👤 {name} · обращение #{ticket.id}"


def _telegram(user: User) -> str:
    if user.telegram_id is None:
        return "Telegram: не привязан"
    if user.telegram_username:
        return f"Telegram: @{user.telegram_username} ({user.telegram_id})"
    return f"Telegram: {user.telegram_id}"


def _email(user: User) -> str | None:
    if user.email is None:
        return None
    mark = "✓" if user.email_verified_at is not None else "✉ не подтверждена"
    return f"Почта: {user.email} {mark}"


def _subscription(subscription: Subscription | None, plan: Plan | None) -> list[str]:
    if subscription is None:
        return ["Подписка: не покупал"]
    title = plan.name.get("ru", plan.code) if plan is not None else "неизвестный тариф"
    days = _days_left(subscription.expires_at)
    when = (
        f"активна до {subscription.expires_at.strftime(DATE_FORMAT)} (осталось {days} дн.)"
        if days >= 0
        else f"истекла {subscription.expires_at.strftime(DATE_FORMAT)} ({-days} дн. назад)"
    )
    renew = "включено" if subscription.auto_renew_enabled else "выключено"
    return [f"Тариф: {title} · {when}", f"Автопродление: {renew}"]


def _days_left(expires_at: datetime) -> int:
    """Дни считаются по календарю, а не по разнице моментов.

    Купленная на 83 дня подписка обязана показать 83 в тот же день: разница
    моментов дала бы 82 — до конца суток не хватает часов, — и сотрудник счёл
    бы это ошибкой начисления.
    """
    return (expires_at.astimezone(UTC).date() - datetime.now(UTC).date()).days


def _devices(devices: tuple[int, int] | None) -> str:
    if devices is None:
        return "Устройства: н/д"
    used, limit = devices
    return f"Устройства: {used} из {limit}"


def _restrictions(user: User) -> list[str]:
    """Ограничения показываются явно: иначе непонятно, почему человек молчит."""
    lines = []
    if user.status is UserStatus.banned:
        lines.append("⛔ Заблокирован")
    if user.support_muted_at is not None:
        lines.append("🔇 Поддержка закрыта")
    return lines
