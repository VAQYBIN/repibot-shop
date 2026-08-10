"""Реферальные дни начисляются с неизменяемых оплаченных заказов."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Order,
    OrderPurpose,
    OrderStatus,
    ReferralReward,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
    User,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.payments import referral_reward_days
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.settings import Settings, get_settings


class ReferralService:
    """Создаёт ровно одну награду в днях на подходящий заказ-источник.

    Вызывает его финализатор оплаты, который уже владеет коммерческой
    транзакцией, поэтому сервис намеренно не коммитит и не ходит в панель.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._plans = PlanRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._entitlements = SubscriptionService(session, self._settings, provisioning=None)

    async def credit_for_order(self, order_id: int) -> ReferralReward | None:
        """Награждает реферера один раз за оплаченный заказ, кроме подарка.

        Длительность берётся из ``Order.duration_days_snapshot``, а не из
        изменяемого тарифа. Блокировка покупателя делает проверку режима
        ``first`` последовательной, даже если две его оплаты финализируются разом.
        """
        order = await self._session.scalar(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        if (
            order is None
            or order.status is not OrderStatus.fulfilled
            or order.purpose is OrderPurpose.gift
        ):
            return None

        purchaser = await self._session.get(User, order.user_id)
        if purchaser is None or purchaser.referred_by_id is None:  # pragma: no cover - FK-backed
            return None
        days = referral_reward_days(
            order.duration_days_snapshot, self._settings.referral_reward_percent
        )
        if days == 0:
            return None

        existing = await self._session.scalar(
            select(ReferralReward)
            .where(ReferralReward.origin_order_id == order.id)
            .with_for_update()
        )
        if existing is not None:
            return existing

        # Блокировка строки не защищает случай «награды ещё не было»: запирать
        # нечего. Эту дыру закрывает та же транзакционная блокировка, что и при
        # создании первой подписки, и берётся она намеренно до поиска награды.
        await self._subscriptions.lock_user_for_entitlement(purchaser.id)
        if self._settings.referral_reward_mode == "first":
            previous = await self._session.scalar(
                select(ReferralReward.id)
                .where(ReferralReward.referee_user_id == purchaser.id)
                .limit(1)
                .with_for_update()
            )
            if previous is not None:
                return None

        await self._subscriptions.lock_user_for_entitlement(purchaser.referred_by_id)
        referrer_subscription = await self._subscriptions.get_for_user_for_update(
            purchaser.referred_by_id
        )
        plan = await self._plans.get(
            referrer_subscription.plan_id if referrer_subscription is not None else order.plan_id
        )
        if plan is None:  # pragma: no cover - plans are retained by design
            return None

        reward = ReferralReward(
            referrer_user_id=purchaser.referred_by_id,
            referee_user_id=purchaser.id,
            origin_order_id=order.id,
            days=days,
        )
        self._session.add(reward)
        await self._session.flush()
        await self._entitlements.apply_entitlement(
            purchaser.referred_by_id,
            plan,
            days,
            source=SubscriptionSource.purchase,
            event_type=SubscriptionEventType.bonus_days,
            actor=SubscriptionActor.system,
            origin_attempt_id=None,
            comment="реферальная награда за оплату",
        )
        return reward
