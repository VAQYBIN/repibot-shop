"""Подписка: единственное место, которое двигает дату окончания."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    OutboxMessage,
    Plan,
    Subscription,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
)
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.trials import TrialRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.domain.subscriptions import (
    SubscriptionState,
    convert_remainder,
    extend,
    resolve_state,
)
from repibot_core.integrations.remnawave.client import RemnawaveError
from repibot_core.services.errors import ServiceError
from repibot_core.services.provisioning import TOPIC_PROVISION, ProvisioningService
from repibot_core.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    plan_code: str
    plan_name: dict[str, str]
    status: SubscriptionState
    started_at: datetime
    expires_at: datetime
    subscription_url: str | None
    traffic_limit_bytes: int
    hwid_device_limit: int
    is_trial: bool


class SubscriptionService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        provisioning: ProvisioningService,
    ) -> None:
        self._session = session
        self._settings = settings
        self._provisioning = provisioning
        self._users = UserRepository(session)
        self._plans = PlanRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._trials = TrialRepository(session)
        self._outbox = OutboxRepository(session)

    async def current(self, user_id: int) -> SubscriptionView | None:
        subscription = await self._subscriptions.get_for_user(user_id)
        if subscription is None:
            return None
        plan = await self._plans.get(subscription.plan_id)
        if plan is None:  # pragma: no cover — тариф не удаляется физически
            msg = "тариф подписки не найден"
            raise ServiceError(msg, "plan_not_found")
        user = await self._users.get(user_id)
        return _view(subscription, plan, user.remnawave_subscription_url if user else None)

    async def trial_available(self, user_id: int) -> bool:
        user = await self._users.get(user_id)
        if user is None or user.telegram_id is None:
            return False
        if await self._plans.active_trial() is None:
            return False
        if await self._subscriptions.get_for_user(user_id) is not None:
            return False
        return await self._trials.get(user.telegram_id) is None

    async def activate_trial(self, user_id: int) -> SubscriptionView:
        user = await self._users.get(user_id)
        if user is None:
            msg = "пользователь не найден"
            raise ServiceError(msg, "not_found")
        if user.telegram_id is None:
            # Почту накрутить тривиально, поэтому триал требует Telegram.
            msg = "для триала нужен привязанный Telegram"
            raise ServiceError(msg, "trial_requires_telegram")
        # Своя подписка проверяется раньше чужого триала: человеку с активной
        # подпиской честнее сказать «она у вас уже есть», а не «триал
        # выдавался» — второе он прочтёт как обвинение в накрутке.
        if await self._subscriptions.get_for_user(user_id) is not None:
            msg = "подписка уже есть"
            raise ServiceError(msg, "subscription_exists")
        if await self._trials.get(user.telegram_id) is not None:
            msg = "триал по этому Telegram уже выдавался"
            raise ServiceError(msg, "trial_already_used")

        plan = await self._plans.active_trial()
        if plan is None:
            msg = "триал не настроен"
            raise ServiceError(msg, "trial_disabled")

        # Отметка о выдаче пишется в той же транзакции, что и подписка: иначе
        # двойной клик успевает пройти проверку дважды и даёт два триала.
        await self._trials.create(telegram_id=user.telegram_id, user_id=user_id)
        return await self.grant_days(
            user_id,
            plan,
            plan.duration_days,
            source=SubscriptionSource.trial,
            event_type=SubscriptionEventType.trial,
            actor=SubscriptionActor.user,
            actor_user_id=user_id,
        )

    async def grant_days(
        self,
        user_id: int,
        plan: Plan,
        days: int,
        *,
        source: SubscriptionSource,
        event_type: SubscriptionEventType,
        actor: SubscriptionActor,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> SubscriptionView:
        """Единственная функция, двигающая expires_at.

        В подпроекте 3 её позовёт финализация платежа; сейчас — триал и
        админское действие. Начисление, журнал и задача выдачи доступа идут
        одной транзакцией: иначе оплата может остаться без выдачи.

        Ноль дней допустим и означает перевод на другой тариф без начисления —
        так выглядит смена тарифа, у которой не осталось оплаченного остатка.
        """
        now = datetime.now(UTC)
        subscription = await self._subscriptions.get_for_user(user_id)
        current_expires_at = subscription.expires_at if subscription is not None else None
        if days == 0:
            expires_at = current_expires_at if current_expires_at is not None else now
        else:
            expires_at = extend(current_expires_at, now, days)

        if subscription is None:
            subscription = await self._subscriptions.create(
                user_id=user_id,
                plan_id=plan.id,
                status=SubscriptionState.pending_provision,
                started_at=now,
                expires_at=expires_at,
                source=source,
            )
        else:
            subscription.plan_id = plan.id
            subscription.expires_at = expires_at
            # Пока панель не приведена к новому состоянию, подписка честно
            # называется невыданной: рабочий статус ставит только примирение.
            subscription.status = SubscriptionState.pending_provision

        await self._subscriptions.add_event(
            user_id=user_id,
            type=event_type,
            days_delta=days,
            plan_id=plan.id,
            actor=actor,
            actor_user_id=actor_user_id,
            comment=comment,
            created_at=now,
        )
        message = await self._outbox.add(topic=TOPIC_PROVISION, payload={"user_id": user_id})
        await self._session.commit()

        url = await self._provision(user_id, plan, message)
        return _view(subscription, plan, url)

    async def change_plan(
        self,
        user_id: int,
        plan_id: int,
        *,
        actor: SubscriptionActor,
        actor_user_id: int | None = None,
    ) -> SubscriptionView:
        """Перевод на другой тариф с сохранением оплаченного остатка."""
        subscription = await self._subscriptions.get_for_user(user_id)
        if subscription is None:
            msg = "подписки нет"
            raise ServiceError(msg, "subscription_missing")

        new_plan = await self._plans.get(plan_id)
        if new_plan is None:
            msg = "тариф не найден"
            raise ServiceError(msg, "plan_not_found")
        if not new_plan.is_active:
            msg = "тариф снят с продажи"
            raise ServiceError(msg, "plan_inactive")

        current_plan = await self._plans.get(subscription.plan_id)
        now = datetime.now(UTC)
        if self._settings.plan_change_keeps_remainder and current_plan is not None:
            days = _remainder_days(
                current_plan, new_plan, expires_at=subscription.expires_at, now=now
            )
            # Остаток уже посчитан от текущей даты окончания, поэтому она
            # обнуляется: иначе оплаченное время учтётся дважды.
            subscription.expires_at = now
        else:
            # Остаток не переносится — срок отсчитывается от нового тарифа.
            days = new_plan.duration_days

        return await self.grant_days(
            user_id,
            new_plan,
            days,
            source=subscription.source,
            event_type=SubscriptionEventType.plan_change,
            actor=actor,
            actor_user_id=actor_user_id,
        )

    async def expire_due(self, *, now: datetime, limit: int = 200) -> int:
        """Переводит просроченные подписки в expired и ставит снятие доступа."""
        due = await self._subscriptions.list_due(now=now, limit=limit)
        for subscription in due:
            subscription.status = SubscriptionState.expired
            await self._subscriptions.add_event(
                user_id=subscription.user_id,
                type=SubscriptionEventType.expired,
                days_delta=0,
                plan_id=subscription.plan_id,
                actor=SubscriptionActor.system,
                actor_user_id=None,
                comment="срок подписки истёк",
                created_at=now,
            )
            # Доступ снимает панель, а не мы: примирение прочитает новый статус
            # и закроет пользователя там же, где открывало.
            await self._outbox.add(topic=TOPIC_PROVISION, payload={"user_id": subscription.user_id})
        await self._session.commit()
        return len(due)

    async def _provision(self, user_id: int, plan: Plan, message: OutboxMessage) -> str | None:
        """Синхронная попытка выдачи доступа. Вызывается только после коммита.

        Отказ здесь не ошибка сценария: задача уже лежит в очереди, и воркер
        доведёт выдачу. Пользователю в этот момент показывается ожидание.

        Вне транзакции намеренно: медленная панель иначе держит блокировки
        строк, а её отказ откатывал бы уже принятое решение о начислении.
        """
        subscription = await self._subscriptions.get_for_user(user_id)
        if subscription is None:  # pragma: no cover — строку записали строкой выше
            return None

        # Статус переводится в рабочий до обращения к панели, а не после:
        # примирение читает его и на pending_provision закрыло бы доступ,
        # который мы как раз выдаём. При отказе панели статус возвращается,
        # и подписка снова честно называется невыданной.
        pending = subscription.status
        subscription.status = resolve_state(
            expires_at=subscription.expires_at,
            now=datetime.now(UTC),
            disabled=False,
            provisioned=True,
            is_trial=plan.is_trial,
        )
        await self._session.commit()

        try:
            state = await asyncio.wait_for(
                self._provisioning.reconcile(user_id),
                timeout=self._settings.remnawave_provision_timeout_seconds,
            )
        except (RemnawaveError, TimeoutError, ServiceError):
            subscription.status = pending
            await self._session.commit()
            logger.info(
                "панель не ответила сразу, выдача уйдёт очередью",
                extra={"user_id": user_id},
            )
            # Ссылка могла быть выдана раньше: продление при лежащей панели —
            # не повод показывать пустое место вместо рабочей ссылки.
            user = await self._users.get(user_id)
            return user.remnawave_subscription_url if user is not None else None

        # Повторять выдачу незачем: панель уже приведена к нашему состоянию.
        await self._outbox.mark_processed(message)
        await self._session.commit()
        return state.subscription_url


def _remainder_days(
    current_plan: Plan, new_plan: Plan, *, expires_at: datetime, now: datetime
) -> int:
    """Остаток текущего тарифа, пересчитанный в дни нового.

    Бесплатный тариф с любой стороны остатка не даёт: стоимость его дня —
    ноль, и делить не на что. Поэтому триал не превращается в дни платного
    тарифа, а оплаченный остаток не переезжает в триал.
    """
    if current_plan.price_rub <= 0 or new_plan.price_rub <= 0:
        return 0
    return convert_remainder(
        expires_at=expires_at,
        now=now,
        current_price_rub=current_plan.price_rub,
        current_duration_days=current_plan.duration_days,
        new_price_rub=new_plan.price_rub,
        new_duration_days=new_plan.duration_days,
    )


def _view(subscription: Subscription, plan: Plan, url: str | None) -> SubscriptionView:
    return SubscriptionView(
        plan_code=plan.code,
        plan_name=plan.name,
        status=subscription.status,
        started_at=subscription.started_at,
        expires_at=subscription.expires_at,
        subscription_url=url,
        traffic_limit_bytes=plan.traffic_limit_bytes,
        hwid_device_limit=plan.hwid_device_limit,
        is_trial=plan.is_trial,
    )
