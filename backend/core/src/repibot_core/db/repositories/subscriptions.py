"""Доступ к подпискам и журналу начислений."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Subscription, SubscriptionEvent
from repibot_core.domain.subscriptions import SubscriptionState

# Статусы, при которых подписка должна существовать в панели. Истёкшую и
# отключённую сверять незачем: панель для них не меняется.
WORKING_STATES = (
    SubscriptionState.trial,
    SubscriptionState.active,
    SubscriptionState.pending_provision,
)


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, user_id: int) -> Subscription | None:
        statement = select(Subscription).where(Subscription.user_id == user_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(self, **fields: Any) -> Subscription:
        subscription = Subscription(**fields)
        self._session.add(subscription)
        await self._session.flush()
        return subscription

    async def list_due(self, *, now: datetime, limit: int) -> list[Subscription]:
        """Подписки, срок которых вышел, но статус ещё рабочий.

        `pending_provision` сюда не входит: доступ ей ещё не выдавали, и
        помечать её истёкшей должен не крон, а неудавшееся примирение.
        """
        statement = (
            select(Subscription)
            .where(
                Subscription.status.in_([SubscriptionState.trial, SubscriptionState.active]),
                Subscription.expires_at <= now,
            )
            .order_by(Subscription.expires_at)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    async def list_for_reconcile(self, *, limit: int, after_id: int = 0) -> list[Subscription]:
        """Страница подписок для сверки с панелью.

        Курсор по идентификатору, а не OFFSET: прогон идёт долго, и сдвиг
        страницы из-за вставки новой подписки пропустил бы чужую строку.
        """
        statement = (
            select(Subscription)
            .where(Subscription.status.in_(WORKING_STATES), Subscription.id > after_id)
            .order_by(Subscription.id)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    async def add_event(self, **fields: Any) -> SubscriptionEvent:
        event = SubscriptionEvent(**fields)
        self._session.add(event)
        await self._session.flush()
        return event
