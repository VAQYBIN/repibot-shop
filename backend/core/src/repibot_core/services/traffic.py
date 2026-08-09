"""Потребление трафика пользователем.

Своего счётчика мы не ведём: трафик считает панель, и любая наша копия
расходилась бы с ней на каждом подключении. Экран кабинета читает панель по
требованию и держит ответ в кэше минуту — опрашивают его часто, а меняется он
редко.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.integrations.remnawave.stats import PanelStats
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError
from repibot_core.services.panel_cache import PanelCache, usage_key


@dataclass(frozen=True, slots=True)
class TrafficDay:
    day: date
    used_bytes: int


@dataclass(frozen=True, slots=True)
class TrafficView:
    used_bytes: int
    lifetime_bytes: int
    limit_bytes: int
    days: list[TrafficDay]


class TrafficService:
    def __init__(
        self, session: AsyncSession, users: PanelUsers, stats: PanelStats, cache: PanelCache
    ) -> None:
        self._session = session
        self._panel = users
        self._stats = stats
        self._cache = cache
        self._users = UserRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._plans = PlanRepository(session)

    async def current(
        self, user_id: int, *, days: int = 30, today: date | None = None
    ) -> TrafficView:
        """Потребление за период, оканчивающийся сегодняшним днём.

        `today` задаётся явно ради тестов: иначе набор дней зависел бы от даты
        прогона и набор разъезжался бы сам собой на следующие сутки.
        """
        panel_id, limit = await self._context(user_id)
        end = today or datetime.now(UTC).date()
        start = end - timedelta(days=days)

        key = usage_key(user_id, start, end)
        stored = await self._cache.get(key)
        if isinstance(stored, dict):
            # Лимит в кэш не кладётся: он наш, читается из тарифа вместе с
            # подпиской и не стоит того, чтобы отставать от неё на минуту.
            return _restore(stored, limit)

        user = await self._panel.get(panel_id)
        if user is None:
            # Идентификатор панели у нас есть, а пользователя по нему нет:
            # доступ выдан не до конца, и цифры показывать нечем.
            msg = "пользователя нет в панели"
            raise ServiceError(msg, "subscription_missing")

        usage = await self._stats.usage(panel_id, start=start, end=end)
        view = TrafficView(
            # Текущее и накопленное — из объекта пользователя, разбивка по дням
            # — из статистики. Оба запроса уходят под один ключ кэша: разъезд
            # между цифрой сверху экрана и суммой столбиков под ней читается
            # как ошибка счёта.
            used_bytes=int(user.userTraffic.usedTrafficBytes),
            lifetime_bytes=int(user.userTraffic.lifetimeUsedTrafficBytes),
            limit_bytes=limit,
            days=[
                TrafficDay(
                    day=date.fromisoformat(category),
                    # День — сумма по всем нодам: человеку нужен трафик за
                    # день, а не разбивка по узлам. Готовое sparklineData не
                    # берётся — в схеме нигде не сказано, что это именно сумма
                    # ряда, а гадать о смысле чужого поля дороже, чем сложить.
                    used_bytes=int(sum(series.data[index] for series in usage.series)),
                )
                for index, category in enumerate(usage.categories)
            ],
        )
        # Пустой ответ панели — это дни без столбиков, а не отказ: у нового
        # пользователя трафика ещё нет, и кэшировать такой ответ тоже нужно.
        await self._cache.put(key, _dump(view))
        return view

    async def _context(self, user_id: int) -> tuple[int, int]:
        """Идентификатор в панели и лимит трафика тарифа."""
        user = await self._users.get(user_id)
        subscription = await self._subscriptions.get_for_user(user_id)
        if user is None or user.remnawave_id is None or subscription is None:
            msg = "подписки нет, трафика тоже"
            raise ServiceError(msg, "subscription_missing")

        plan = await self._plans.get(subscription.plan_id)
        # Ноль в тарифе означает «без ограничения» — так же, как в панели.
        limit = plan.traffic_limit_bytes if plan is not None else 0
        return user.remnawave_id, limit


def _dump(view: TrafficView) -> dict[str, Any]:
    """Представление в вид, переживающий JSON: даты — строками."""
    return {
        "used_bytes": view.used_bytes,
        "lifetime_bytes": view.lifetime_bytes,
        "days": [{"day": day.day.isoformat(), "used_bytes": day.used_bytes} for day in view.days],
    }


def _restore(stored: dict[str, Any], limit: int) -> TrafficView:
    return TrafficView(
        used_bytes=int(stored["used_bytes"]),
        lifetime_bytes=int(stored["lifetime_bytes"]),
        limit_bytes=limit,
        days=[
            TrafficDay(day=date.fromisoformat(str(item["day"])), used_bytes=int(item["used_bytes"]))
            for item in stored["days"]
        ],
    )
