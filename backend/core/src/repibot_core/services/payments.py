"""Единая транзакционная точка, где подтверждённая оплата становится правом."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    GiftVoucher,
    NotificationDelivery,
    Order,
    OrderPurpose,
    OrderStatus,
    PaymentAttempt,
    PaymentProvider,
    PaymentStatus,
    Plan,
    PromoReservation,
    ReferralReward,
    Subscription,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
    User,
)
from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.payments import referral_reward_days
from repibot_core.domain.subscriptions import convert_remainder
from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus
from repibot_core.services.errors import ServiceError
from repibot_core.services.provisioning import TOPIC_PROVISION
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class FinalizationResult:
    order_id: int
    already_finalized: bool
    expired: bool = False


class YooKassaVerifier(Protocol):
    async def get_payment(self, payment_id: str) -> YooKassaPayment: ...


class PaymentService:
    """Ставит все локальные последствия платежа до единственного commit."""

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._orders = OrderRepository(session)
        self._attempts = PaymentAttemptRepository(session)
        self._plans = PlanRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._outbox = OutboxRepository(session)
        # apply_entitlement намеренно не использует provisioning: финализация
        # не имеет права открывать HTTP-клиент при удержании row locks.
        self._entitlements = SubscriptionService(session, self._settings, provisioning=None)

    async def finalize_success(self, attempt_id: int) -> FinalizationResult:
        """Фиксирует подтверждённую попытку и все её локальные последствия."""
        async with self._session.begin():
            order_id = await self._session.scalar(
                select(PaymentAttempt.order_id).where(PaymentAttempt.id == attempt_id)
            )
            if order_id is None:
                raise ServiceError("платёжная попытка не найдена", "payment_attempt_not_found")

            # Общий порядок удержания строк: order → attempt → subscription →
            # promo/voucher/referral. Первое чтение выше не блокирует строку и
            # нужно только чтобы узнать родительский order для первого lock.
            order = await self._orders.get_for_update(order_id)
            if order is None:  # pragma: no cover — FK attempt.order_id это исключает
                raise ServiceError("заказ не найден", "order_not_found")
            attempt = await self._attempts.get_for_update(attempt_id)
            if attempt is None or attempt.order_id != order.id:  # pragma: no cover
                raise ServiceError("платёжная попытка не найдена", "payment_attempt_not_found")

            if order.status is OrderStatus.expired:
                return FinalizationResult(order_id=order.id, already_finalized=False, expired=True)
            if order.status is OrderStatus.pending and order.expires_at <= datetime.now(UTC):
                await self._expire_locked_order(order)
                return FinalizationResult(order_id=order.id, already_finalized=False, expired=True)
            if order.status is OrderStatus.fulfilled:
                return FinalizationResult(order_id=order.id, already_finalized=True)
            self._validate_verified_attempt(order, attempt)

            purchaser = await self._session.get(User, order.user_id)
            if purchaser is None:  # pragma: no cover — FK order.user_id это исключает
                raise ServiceError("пользователь заказа не найден", "user_not_found")

            subscription_users = {order.user_id}
            if purchaser.referred_by_id is not None:
                subscription_users.add(purchaser.referred_by_id)
            locked_subscriptions: dict[int, Subscription | None] = {}
            for user_id in sorted(subscription_users):
                await self._subscriptions.lock_user_for_entitlement(user_id)
                locked_subscriptions[user_id] = await self._subscriptions.get_for_user_for_update(
                    user_id
                )

            # Последующие сущности всегда запрашиваются после subscriptions,
            # даже если соответствующая строка ещё не создана: это сохраняет
            # единый порядок при развитии правил промо, gift и referral.
            reservation = (
                await self._session.execute(
                    select(PromoReservation)
                    .where(PromoReservation.order_id == order.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            await self._session.execute(
                select(GiftVoucher).where(GiftVoucher.order_id == order.id).with_for_update()
            )
            existing_reward = (
                await self._session.execute(
                    select(ReferralReward)
                    .where(ReferralReward.origin_order_id == order.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()

            plan = await self._plans.get(order.plan_id)
            if plan is None:  # pragma: no cover — план не удаляется физически
                raise ServiceError("тариф заказа не найден", "plan_not_found")

            if order.purpose is not OrderPurpose.gift:
                subscription = locked_subscriptions[order.user_id]
                entitlement_days = self._entitlement_days(order, subscription)
                event_type = self._event_type(order, subscription)
                applied = await self._entitlements.apply_entitlement(
                    order.user_id,
                    plan,
                    entitlement_days,
                    source=SubscriptionSource.purchase,
                    event_type=event_type,
                    actor=SubscriptionActor.system,
                    origin_attempt_id=attempt.id,
                )
                # Новый остаток тоже должен знать согласованную при покупке
                # стоимость, иначе будущая смена тарифа прочитает Plan после
                # редактирования цены в админке.
                applied.entitlement_price_rub = order.price_rub_snapshot
                applied.entitlement_duration_days = order.duration_days_snapshot
                await self._outbox.add(TOPIC_PROVISION, {"user_id": order.user_id})

            if reservation is not None and reservation.consumed_at is None:
                reservation.consumed_at = datetime.now(UTC)

            await self._stage_referral_bonus(
                order=order,
                purchaser=purchaser,
                plan=plan,
                existing_reward=existing_reward,
                locked_subscription=(
                    locked_subscriptions[purchaser.referred_by_id]
                    if purchaser.referred_by_id is not None
                    else None
                ),
            )
            self._session.add(
                NotificationDelivery(
                    order_id=order.id,
                    user_id=order.user_id,
                    kind="payment_succeeded",
                    channel="in_app",
                )
            )
            order.status = OrderStatus.fulfilled
            order.fulfilled_at = datetime.now(UTC)

        return FinalizationResult(order_id=order.id, already_finalized=False)

    async def verify_yookassa_callback(
        self, provider_payment_id: str, yookassa: YooKassaVerifier
    ) -> FinalizationResult | None:
        """Проверяет hint у YooKassa и только затем вызывает локальный финализатор.

        Сеть намеренно находится до ``session.begin()``: финализатор удерживает
        коммерческие блокировки и обязан оставаться полностью локальным.
        """
        payment = await yookassa.get_payment(provider_payment_id)
        should_finalize = False
        async with self._session.begin():
            order_id = await self._session.scalar(
                select(PaymentAttempt.order_id).where(
                    PaymentAttempt.provider == PaymentProvider.yookassa,
                    PaymentAttempt.provider_payment_id == payment.id,
                )
            )
            if order_id is None:
                return None
            order = await self._orders.get_for_update(order_id)
            if order is None:  # pragma: no cover — FK attempt.order_id это исключает
                return None
            attempt = await self._session.scalar(
                select(PaymentAttempt)
                .where(
                    PaymentAttempt.provider == PaymentProvider.yookassa,
                    PaymentAttempt.provider_payment_id == payment.id,
                )
                .with_for_update()
            )
            if attempt is None:  # pragma: no cover — строки выбраны одним ключом
                return None

            self._record_yookassa_verification(attempt, payment)
            if order.status is OrderStatus.pending and order.expires_at <= datetime.now(UTC):
                await self._expire_locked_order(order)
                return None
            should_finalize = (
                order.status is OrderStatus.pending
                and payment.status is YooKassaPaymentStatus.succeeded
                and self._yookassa_amount_matches(order, payment)
            )

        if should_finalize:
            return await self.finalize_success(attempt.id)
        return None

    async def expire_due_orders(self, *, now: datetime) -> int:
        """Закрывает просроченные заказы и освобождает их промо-резервы атомарно."""
        async with self._session.begin():
            orders = list(
                (
                    await self._session.scalars(
                        select(Order)
                        .where(Order.status == OrderStatus.pending, Order.expires_at <= now)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for order in orders:
                await self._expire_locked_order(order)
        return len(orders)

    @staticmethod
    def _record_yookassa_verification(attempt: PaymentAttempt, payment: YooKassaPayment) -> None:
        """Запоминает именно ответ провайдера — ключ дедупликации id + status."""
        attempt.status = (
            PaymentStatus.succeeded
            if payment.status is YooKassaPaymentStatus.succeeded
            else PaymentStatus.canceled
            if payment.status is YooKassaPaymentStatus.canceled
            else PaymentStatus.pending
        )
        attempt.verified_payload = {
            "amount": format(payment.amount_rub, ".2f"),
            "currency": payment.currency,
            "status": payment.status.value,
        }
        attempt.verified_at = datetime.now(UTC)

    @staticmethod
    def _yookassa_amount_matches(order: Order, payment: YooKassaPayment) -> bool:
        return payment.currency == "RUB" and payment.amount_rub == order.amount_due_rub

    async def _expire_locked_order(self, order: Order) -> None:
        """Освобождает неиспользованный промокод в той же транзакции, что и expiry."""
        await self._session.execute(
            delete(PromoReservation).where(
                PromoReservation.order_id == order.id,
                PromoReservation.consumed_at.is_(None),
            )
        )
        order.status = OrderStatus.expired

    def _validate_verified_attempt(self, order: Order, attempt: PaymentAttempt) -> None:
        if attempt.status is not PaymentStatus.succeeded or attempt.verified_payload is None:
            raise ServiceError("оплата не подтверждена", "payment_not_verified")
        payload = attempt.verified_payload
        currency = payload.get("currency")
        amount = payload.get("amount")
        if attempt.provider is PaymentProvider.yookassa:
            try:
                amount_matches = Decimal(str(amount)) == order.amount_due_rub
            except (InvalidOperation, ValueError):
                amount_matches = False
            if currency != "RUB" or not amount_matches:
                raise ServiceError(
                    "сумма подтверждённой оплаты не совпадает с заказом", "payment_mismatch"
                )
        elif attempt.provider is PaymentProvider.stars:
            if currency != "XTR" or amount != order.price_stars_snapshot:
                raise ServiceError(
                    "сумма подтверждённой оплаты не совпадает с заказом", "payment_mismatch"
                )

    def _entitlement_days(self, order: Order, subscription: Subscription | None) -> int:
        if subscription is None or subscription.plan_id == order.plan_id:
            return order.duration_days_snapshot
        if subscription.entitlement_price_rub <= 0 or order.price_rub_snapshot <= 0:
            return order.duration_days_snapshot
        carried = convert_remainder(
            expires_at=subscription.expires_at,
            now=datetime.now(UTC),
            current_price_rub=subscription.entitlement_price_rub,
            current_duration_days=subscription.entitlement_duration_days,
            new_price_rub=order.price_rub_snapshot,
            new_duration_days=order.duration_days_snapshot,
        )
        # apply_entitlement продлевает от expires_at. Перед этим переносим
        # именно денежный остаток старого права, затем добавляем купленный срок.
        subscription.expires_at = datetime.now(UTC) + timedelta(days=carried)
        return order.duration_days_snapshot

    def _event_type(self, order: Order, subscription: Subscription | None) -> SubscriptionEventType:
        if order.purpose is OrderPurpose.renew or (
            subscription is not None and subscription.plan_id == order.plan_id
        ):
            return SubscriptionEventType.renew
        if subscription is not None:
            return SubscriptionEventType.plan_change
        return SubscriptionEventType.purchase

    async def _stage_referral_bonus(
        self,
        *,
        order: Order,
        purchaser: User,
        plan: Plan,
        existing_reward: ReferralReward | None,
        locked_subscription: Subscription | None,
    ) -> None:
        if (
            purchaser.referred_by_id is None
            or existing_reward is not None
            or order.purpose is OrderPurpose.gift
        ):
            return
        days = referral_reward_days(
            order.duration_days_snapshot, self._settings.referral_reward_percent
        )
        if days == 0:
            return
        if self._settings.referral_reward_mode == "first":
            prior = await self._session.scalar(
                select(ReferralReward.id)
                .where(ReferralReward.referee_user_id == purchaser.id)
                .limit(1)
                .with_for_update()
            )
            if prior is not None:
                return
        self._session.add(
            ReferralReward(
                referrer_user_id=purchaser.referred_by_id,
                referee_user_id=purchaser.id,
                origin_order_id=order.id,
                days=days,
            )
        )
        referrer_plan = plan
        if locked_subscription is not None:
            saved_plan = await self._plans.get(locked_subscription.plan_id)
            if saved_plan is not None:
                referrer_plan = saved_plan
        await self._entitlements.apply_entitlement(
            purchaser.referred_by_id,
            referrer_plan,
            days,
            source=SubscriptionSource.purchase,
            event_type=SubscriptionEventType.bonus_days,
            actor=SubscriptionActor.system,
            origin_attempt_id=None,
            comment="реферальная награда за оплату",
        )
