"""Хранилище заказов и идемпотентных обращений к провайдерам."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Order, OrderPurpose, OrderStatus, PaymentAttempt, PaymentProvider
from repibot_core.db.models.plan import Plan


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        *,
        user_id: int,
        plan: Plan,
        client_key: str,
        expires_at: datetime,
        purpose: OrderPurpose = OrderPurpose.purchase,
        gross_rub: Decimal | None = None,
        discount_rub: Decimal | None = None,
        promo_code_id: int | None = None,
    ) -> Order:
        """Создаёт заказ, копируя всё нужное для последующей выдачи доступа."""
        gross = plan.price_rub if gross_rub is None else gross_rub
        discount = Decimal("0.00") if discount_rub is None else discount_rub
        order = Order(
            user_id=user_id,
            purpose=purpose,
            plan_id=plan.id,
            plan_code_snapshot=plan.code,
            plan_name_snapshot=dict(plan.name),
            duration_days_snapshot=plan.duration_days,
            price_rub_snapshot=plan.price_rub,
            price_stars_snapshot=plan.price_stars,
            gross_rub=gross,
            discount_rub=discount,
            amount_due_rub=gross - discount,
            promo_code_id=promo_code_id,
            client_key=client_key,
            expires_at=expires_at,
            status=OrderStatus.pending,
        )
        self._session.add(order)
        await self._session.flush()
        return order

    async def get_for_update(self, order_id: int) -> Order | None:
        statement = select(Order).where(Order.id == order_id).with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()


class PaymentAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        *,
        order_id: int,
        provider: PaymentProvider,
        attempt_no: int,
        provider_key: str,
        **fields: Any,
    ) -> PaymentAttempt:
        """Возвращает уже созданную попытку по стабильному ключу повтора."""
        statement = select(PaymentAttempt).where(
            PaymentAttempt.provider == provider, PaymentAttempt.provider_key == provider_key
        )
        existing = (await self._session.execute(statement)).scalar_one_or_none()
        if existing is not None:
            return existing

        attempt = PaymentAttempt(
            order_id=order_id,
            provider=provider,
            attempt_no=attempt_no,
            provider_key=provider_key,
            **fields,
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt
