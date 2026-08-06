"""Приведение панели к нашему состоянию.

Одна функция на все случаи: выдача доступа после оплаты, активация триала,
смена тарифа, разбор очереди и крон-реконсиляция. Разные пути расходились бы
в мелочах, а расхождение здесь означает пользователя без доступа.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.subscriptions import SubscriptionState, panel_username
from repibot_core.integrations.remnawave.types import (
    CreateUserBody,
    PanelUser,
    UpdateUserBody,
)
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError

logger = logging.getLogger(__name__)

TOPIC_PROVISION = "panel.provision"

# Тег отличает пользователей панели, которых ведём мы, от заведённых админом
# руками. Чужих реконсиляция не трогает.
PANEL_TAG = "REPIBOT"

# Статусы, при которых доступ в панели должен быть открыт.
_ALLOWED = (SubscriptionState.trial, SubscriptionState.active)


@dataclass(frozen=True, slots=True)
class PanelState:
    panel_id: int
    short_uuid: str
    subscription_url: str


class ProvisioningService:
    def __init__(self, session: AsyncSession, users: PanelUsers) -> None:
        self._session = session
        self._panel = users
        self._users = UserRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._plans = PlanRepository(session)

    async def reconcile(self, user_id: int) -> PanelState:
        """Приводит пользователя панели к нашему состоянию и возвращает его.

        Дату окончания считаем только мы, поэтому в панель уходит абсолютное
        значение. Маршрут actions/extend не используется намеренно: он двигает
        дату на стороне панели, и повтор задачи из очереди начислил бы дни
        второй раз.
        """
        user = await self._users.get(user_id)
        if user is None:
            msg = "пользователь не найден"
            raise ServiceError(msg, "not_found")

        subscription = await self._subscriptions.get_for_user(user_id)
        if subscription is None:
            msg = "подписки нет, приводить панель не к чему"
            raise ServiceError(msg, "subscription_missing")

        plan = await self._plans.get(subscription.plan_id)
        if plan is None:  # pragma: no cover — тариф не удаляется физически
            msg = "тариф подписки не найден"
            raise ServiceError(msg, "plan_not_found")

        username = panel_username(user_id)
        desired: dict[str, Any] = {
            "status": "ACTIVE" if subscription.status in _ALLOWED else "DISABLED",
            "expireAt": subscription.expires_at,
            "trafficLimitBytes": plan.traffic_limit_bytes,
            "trafficLimitStrategy": plan.traffic_reset_strategy.value,
            "hwidDeviceLimit": plan.hwid_device_limit,
            "activeInternalSquads": [str(uuid) for uuid in plan.internal_squad_uuids],
        }

        existing = await self._find(user.remnawave_id, username)
        panel_user = (
            await self._create(username, user.telegram_id, user.email, desired)
            if existing is None
            else await self._update_if_needed(existing, desired)
        )

        user.remnawave_id = int(panel_user.id)
        user.remnawave_short_uuid = panel_user.shortUuid
        user.remnawave_subscription_url = panel_user.subscriptionUrl
        await self._session.commit()

        return PanelState(
            panel_id=int(panel_user.id),
            short_uuid=panel_user.shortUuid,
            subscription_url=panel_user.subscriptionUrl,
        )

    async def _find(self, panel_id: int | None, username: str) -> PanelUser | None:
        """Ищет пользователя панели, не создавая дублей.

        Числовой идентификатор мог потеряться — например, база восстановлена
        из бэкапа раньше панели. Поиск по имени возвращает того же самого
        пользователя, потому что имя выводится из нашего идентификатора.
        """
        if panel_id is not None:
            found = await self._panel.get(panel_id)
            if found is not None:
                return found
        return await self._panel.resolve(username=username)

    async def _create(
        self,
        username: str,
        telegram_id: int | None,
        email: str | None,
        desired: dict[str, Any],
    ) -> PanelUser:
        body = CreateUserBody(
            username=username,
            tag=PANEL_TAG,
            telegramId=telegram_id,
            email=email,
            **desired,
        )
        return await self._panel.create(body)

    async def _update_if_needed(self, existing: PanelUser, desired: dict[str, Any]) -> PanelUser:
        """Пишет в панель только при расхождении.

        Пустой PATCH стоит нам запроса, а панели — записи в журнал изменений
        и события вебхука, на которое мы же и отреагируем.
        """
        if existing.tag != PANEL_TAG:
            logger.warning(
                "пользователь панели заведён мимо нас, правка пропущена",
                extra={"panel_user_id": existing.id, "panel_tag": existing.tag},
            )
            return existing

        current: dict[str, Any] = {
            "status": existing.status.value,
            # До секунды: панель хранит дату с миллисекундами, у нас в базе
            # микросекунды. Сравнение как есть расходилось бы всегда, и
            # реконсиляция писала бы в панель на каждом прогоне.
            "expireAt": existing.expireAt.replace(microsecond=0),
            "trafficLimitBytes": float(existing.trafficLimitBytes),
            "trafficLimitStrategy": existing.trafficLimitStrategy.value,
            "hwidDeviceLimit": existing.hwidDeviceLimit,
            "activeInternalSquads": sorted(
                str(squad.uuid) for squad in existing.activeInternalSquads
            ),
        }
        wanted = dict(desired)
        wanted["expireAt"] = desired["expireAt"].replace(microsecond=0)
        wanted["trafficLimitBytes"] = float(desired["trafficLimitBytes"])
        wanted["activeInternalSquads"] = sorted(desired["activeInternalSquads"])

        if current == wanted:
            return existing

        # Панели уходят все поля желаемого состояния: фасад отправляет только
        # явно заданные, и частичное тело оставило бы расхождение неисправленным.
        return await self._panel.update(UpdateUserBody(id=int(existing.id), **desired))


def build_provision_handler(
    session_factory: async_sessionmaker[AsyncSession], users: PanelUsers
) -> Any:
    """Обработчик темы panel.provision для очереди надёжной доставки.

    Своя сессия, а не сессия диспетчера: разбор очереди коммитит собственную
    транзакцию, и вмешиваться в неё выдачей доступа нельзя.
    """

    async def handle(payload: dict[str, Any]) -> None:
        async with session_factory() as session:
            await ProvisioningService(session, users).reconcile(int(payload["user_id"]))

    return handle
