"""Единая транзакционная точка, где подтверждённая оплата становится правом."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    GiftVoucher,
    Order,
    OrderPurpose,
    OrderStatus,
    PaymentAttempt,
    PaymentProvider,
    PaymentStatus,
    PromoReservation,
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
from repibot_core.domain.subscriptions import convert_remainder
from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus
from repibot_core.services.errors import ServiceError
from repibot_core.services.payment_methods import PaymentMethodService
from repibot_core.services.payment_notifications import NotificationService
from repibot_core.services.promotions import PromotionService
from repibot_core.services.provisioning import TOPIC_PROVISION
from repibot_core.services.referrals import ReferralService
from repibot_core.services.subscriptions import SubscriptionService
from repibot_core.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class FinalizationResult:
    order_id: int
    already_finalized: bool
    expired: bool = False


class YooKassaVerifier(Protocol):
    async def get_payment(self, payment_id: str) -> YooKassaPayment: ...


class YooKassaCreator(Protocol):
    async def create_payment(
        self,
        *,
        idempotence_key: str,
        amount_rub: Decimal,
        return_url: str,
        description: str,
        save_payment_method: bool,
        payment_method_id: str | None = None,
    ) -> YooKassaPayment: ...


@dataclass(frozen=True, slots=True)
class CreatedOrder:
    order: Order
    confirmation_url: str | None


@dataclass(frozen=True, slots=True)
class CreatedStarsOrder:
    """Заказ Stars в ожидании и непрозрачный payload для инвойса Telegram."""

    order: Order
    invoice_payload: str | None
    handoff_reference: str | None


@dataclass(frozen=True, slots=True)
class StarsInvoice:
    """Значения для SendInvoice, которые определяет сервер, а не клиент."""

    title: str
    description: str
    invoice_payload: str
    price_stars: int


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

    async def create_manual_yookassa_order(
        self,
        *,
        user_id: int,
        plan_id: int,
        purpose: OrderPurpose,
        client_key: str,
        promo_code: str | None,
        yookassa: YooKassaCreator,
    ) -> CreatedOrder:
        """Создаёт ровно один серверный снимок и YooKassa-платёж для него.

        Клиентский ключ сначала фиксируется локально. Повтор затем безопасно
        отправить и провайдеру: ключ там привязан к пользователю, поэтому два
        разных покупателя с одинаковым UUID не разделят платёж.
        """
        # Проверка входа в API уже открыла транзакцию на чтение. Коммерческой
        # транзакцией ниже владеет этот сервис, поэтому читающую нужно закрыть
        # до её начала.
        if self._session.in_transaction():
            await self._session.commit()
        provider_key = self._provider_key(user_id, client_key)
        existing: Order | None = None
        stored_confirmation_url: str | None = None
        async with self._session.begin():
            await self._session.execute(
                select(func.pg_advisory_xact_lock(self._order_lock_key(user_id, client_key)))
            )
            existing = await self._session.scalar(
                select(Order).where(Order.user_id == user_id, Order.client_key == client_key)
            )
            if existing is None:
                plan = await self._plans.get(plan_id)
                if plan is None:
                    raise ServiceError("тариф не найден", "plan_inactive")
                if not plan.is_active or not plan.is_visible or plan.is_trial:
                    raise ServiceError("тариф недоступен", "plan_inactive")
                if promo_code:
                    if purpose not in (OrderPurpose.purchase, OrderPurpose.renew):
                        raise ServiceError("промокод недоступен", "promo_unavailable")
                    quote = await PromotionService(self._session).prepare(
                        user_id=user_id, code=promo_code, gross_rub=plan.price_rub
                    )
                else:
                    quote = None
                existing = await self._orders.create_pending(
                    user_id=user_id,
                    plan=plan,
                    client_key=client_key,
                    expires_at=datetime.now(UTC)
                    + timedelta(minutes=self._settings.yookassa_order_ttl_minutes),
                    purpose=purpose,
                    gross_rub=plan.price_rub,
                    discount_rub=quote.discount_rub if quote is not None else Decimal("0.00"),
                    promo_code_id=quote.promo_id if quote is not None else None,
                )
                if quote is not None:
                    await PromotionService(self._session).reserve_prepared(
                        order=existing, user_id=user_id, quote=quote
                    )
                await self._attempts.get_or_create(
                    order_id=existing.id,
                    provider=PaymentProvider.yookassa,
                    attempt_no=1,
                    provider_key=provider_key,
                )
            elif existing.status is OrderStatus.pending and existing.expires_at <= datetime.now(
                UTC
            ):
                await self._expire_locked_order(existing)
            elif existing.status is OrderStatus.pending:
                attempt = await self._session.scalar(
                    select(PaymentAttempt).where(
                        PaymentAttempt.order_id == existing.id,
                        PaymentAttempt.provider == PaymentProvider.yookassa,
                    )
                )
                if attempt is not None and attempt.verified_payload is not None:
                    value = attempt.verified_payload.get("confirmation_url")
                    if isinstance(value, str):
                        stored_confirmation_url = value

        assert existing is not None  # транзакция выше либо создала заказ, либо нашла его
        if existing.status is OrderStatus.expired or existing.expires_at <= datetime.now(UTC):
            raise ServiceError("заказ истёк", "order_expired")
        if existing.status is not OrderStatus.pending:
            return CreatedOrder(order=existing, confirmation_url=None)
        if stored_confirmation_url is not None:
            return CreatedOrder(order=existing, confirmation_url=stored_confirmation_url)

        payment = await yookassa.create_payment(
            idempotence_key=provider_key,
            amount_rub=existing.amount_due_rub,
            return_url=self._settings.public_app_url,
            description=f"Re:Pibot: {existing.plan_code_snapshot}",
            # Флаг намеренно не передаётся: без него YooKassa показывает на
            # форме галочку «запомнить карту», и решает плательщик, а не мы.
            save_payment_method=False,
        )
        if payment.currency != "RUB" or payment.amount_rub != existing.amount_due_rub:
            raise ServiceError("провайдер вернул неверную сумму", "provider_unavailable")
        if payment.confirmation_url is None:
            raise ServiceError("провайдер не вернул ссылку оплаты", "provider_unavailable")

        async with self._session.begin():
            attempt = await self._attempts.get_or_create(
                order_id=existing.id,
                provider=PaymentProvider.yookassa,
                attempt_no=1,
                provider_key=provider_key,
            )
            attempt.provider_payment_id = payment.id
            # Это единственный нужный публичному повтору фрагмент ответа
            # провайдера; секреты и оригинальное тело никогда не сохраняются.
            attempt.verified_payload = {"confirmation_url": payment.confirmation_url}

        return CreatedOrder(order=existing, confirmation_url=payment.confirmation_url)

    async def create_stars_order(
        self,
        *,
        user_id: int,
        plan_id: int,
        purpose: OrderPurpose,
        client_key: str,
        promo_code: str | None,
    ) -> CreatedStarsOrder:
        """Готовит серверное состояние инвойса Stars; браузер денег не трогает."""
        if self._session.in_transaction():
            await self._session.commit()
        existing: Order | None = None
        attempt: PaymentAttempt | None = None
        async with self._session.begin():
            await self._session.execute(
                select(func.pg_advisory_xact_lock(self._order_lock_key(user_id, client_key)))
            )
            existing = await self._session.scalar(
                select(Order)
                .where(Order.user_id == user_id, Order.client_key == client_key)
                .with_for_update()
            )
            if existing is None:
                plan = await self._plans.get(plan_id)
                if plan is None:
                    raise ServiceError("тариф не найден", "plan_not_found")
                if not plan.is_active or not plan.is_visible or plan.is_trial:
                    raise ServiceError("тариф недоступен", "plan_inactive")
                if promo_code:
                    raise ServiceError("промокод недоступен", "promo_unavailable")
                existing = await self._orders.create_pending(
                    user_id=user_id,
                    plan=plan,
                    client_key=client_key,
                    expires_at=datetime.now(UTC)
                    + timedelta(minutes=self._settings.stars_order_ttl_minutes),
                    purpose=purpose,
                )
                attempt = await self._attempts.get_or_create(
                    order_id=existing.id,
                    provider=PaymentProvider.stars,
                    attempt_no=1,
                    provider_key=token_urlsafe(32),
                    handoff_token=token_urlsafe(32),
                )
            elif existing.status is OrderStatus.pending and existing.expires_at <= datetime.now(
                UTC
            ):
                await self._expire_locked_order(existing)
            elif existing.status is OrderStatus.pending:
                attempt = await self._session.scalar(
                    select(PaymentAttempt).where(
                        PaymentAttempt.order_id == existing.id,
                        PaymentAttempt.provider == PaymentProvider.stars,
                    )
                )
            if attempt is not None and attempt.handoff_token is None:
                # Миграция оставила старые попытки без токена; первый же повтор
                # запроса безопасно выдаёт его.
                attempt.handoff_token = token_urlsafe(32)

        assert existing is not None
        if existing.status is OrderStatus.expired or existing.expires_at <= datetime.now(UTC):
            raise ServiceError("заказ истёк", "order_expired")
        if existing.status is not OrderStatus.pending:
            return CreatedStarsOrder(order=existing, invoice_payload=None, handoff_reference=None)
        if attempt is None:
            raise ServiceError(
                "для заказа уже выбран другой способ оплаты", "payment_provider_mismatch"
            )
        return CreatedStarsOrder(
            order=existing,
            invoice_payload=self._stars_invoice_payload(attempt.provider_key),
            handoff_reference=attempt.handoff_token,
        )

    async def next_stars_invoice(self, user_id: int, handoff_reference: str) -> StarsInvoice | None:
        """Разбирает непрозрачную передачу владельца, не раскрывая инвойс браузеру."""
        if self._session.in_transaction():
            await self._session.commit()
        async with self._session.begin():
            row = (
                await self._session.execute(
                    select(PaymentAttempt, Order)
                    .join(Order, Order.id == PaymentAttempt.order_id)
                    .where(
                        Order.user_id == user_id,
                        Order.status == OrderStatus.pending,
                        Order.expires_at > datetime.now(UTC),
                        PaymentAttempt.provider == PaymentProvider.stars,
                        PaymentAttempt.status == PaymentStatus.pending,
                        PaymentAttempt.handoff_token == handoff_reference,
                    )
                    .limit(1)
                )
            ).one_or_none()
            if row is None:
                return None
            attempt, order = row
            title = order.plan_name_snapshot.get("ru") or order.plan_code_snapshot
            return StarsInvoice(
                title=title,
                description=f"Re:Pibot: {order.plan_code_snapshot}",
                invoice_payload=self._stars_invoice_payload(attempt.provider_key),
                price_stars=order.price_stars_snapshot,
            )

    async def authorize_stars_attempt(
        self,
        *,
        invoice_payload: str,
        user_id: int,
        total_amount: int,
        currency: str,
        pre_checkout_id: str,
    ) -> int | None:
        """Проверяет pre-checkout до того, как Telegram спишет звёзды."""
        return await self._validated_stars_attempt(
            invoice_payload=invoice_payload,
            user_id=user_id,
            total_amount=total_amount,
            currency=currency,
            pre_checkout_id=pre_checkout_id,
            telegram_payment_charge_id=None,
            mark_succeeded=False,
        )

    async def confirm_stars_success(
        self,
        *,
        invoice_payload: str,
        user_id: int,
        total_amount: int,
        currency: str,
        telegram_payment_charge_id: str,
    ) -> int | None:
        """Записывает successful_payment Telegram для общего финализатора."""
        return await self._validated_stars_attempt(
            invoice_payload=invoice_payload,
            user_id=user_id,
            total_amount=total_amount,
            currency=currency,
            pre_checkout_id=None,
            telegram_payment_charge_id=telegram_payment_charge_id,
            mark_succeeded=True,
        )

    async def _validated_stars_attempt(
        self,
        *,
        invoice_payload: str,
        user_id: int,
        total_amount: int,
        currency: str,
        pre_checkout_id: str | None,
        telegram_payment_charge_id: str | None,
        mark_succeeded: bool,
    ) -> int | None:
        reference = self._stars_invoice_reference(invoice_payload)
        if (
            reference is None
            or type(total_amount) is not int
            or currency != "XTR"
            or (not mark_succeeded and not self._valid_stars_provider_id(pre_checkout_id))
            or (mark_succeeded and not self._valid_stars_provider_id(telegram_payment_charge_id))
        ):
            return None
        if self._session.in_transaction():
            await self._session.commit()
        async with self._session.begin():
            durable_id = telegram_payment_charge_id if mark_succeeded else pre_checkout_id
            assert durable_id is not None  # сужено проверкой на границе выше
            await self._session.execute(
                select(func.pg_advisory_xact_lock(self._stars_identity_lock_key(durable_id)))
            )
            attempt_id = await self._session.scalar(
                select(PaymentAttempt.id).where(
                    PaymentAttempt.provider == PaymentProvider.stars,
                    PaymentAttempt.provider_key == reference,
                )
            )
            if attempt_id is None:
                return None
            order_id = await self._session.scalar(
                select(PaymentAttempt.order_id).where(PaymentAttempt.id == attempt_id)
            )
            if order_id is None:  # pragma: no cover — selected attempt has a mandatory FK
                return None
            order = await self._orders.get_for_update(order_id)
            attempt = await self._attempts.get_for_update(attempt_id)
            if attempt is None or order is None:
                return None
            paid_stars = (
                attempt.provider is PaymentProvider.stars
                and attempt.status is PaymentStatus.succeeded
            )
            if (
                order.status is OrderStatus.pending
                and order.expires_at <= datetime.now(UTC)
                and not paid_stars
            ):
                await self._expire_locked_order(order)
                return None
            if (
                attempt.provider is not PaymentProvider.stars
                or order.status is not OrderStatus.pending
                or order.user_id != user_id
                or total_amount != order.price_stars_snapshot
            ):
                return None
            if not mark_succeeded:
                assert pre_checkout_id is not None
                claimed = await self._session.scalar(
                    select(PaymentAttempt.id).where(
                        PaymentAttempt.stars_pre_checkout_id == pre_checkout_id
                    )
                )
                if claimed is not None and claimed != attempt.id:
                    return None
                if attempt.stars_pre_checkout_id is None:
                    attempt.stars_pre_checkout_id = pre_checkout_id
                    attempt.stars_authorized_at = datetime.now(UTC)
                elif attempt.stars_pre_checkout_id != pre_checkout_id:
                    return None
                return attempt.id

            assert telegram_payment_charge_id is not None
            existing_charge = await self._session.scalar(
                select(PaymentAttempt.id).where(
                    PaymentAttempt.telegram_payment_charge_id == telegram_payment_charge_id
                )
            )
            if existing_charge is not None and existing_charge != attempt.id:
                return None
            expected_payload = {
                "amount": total_amount,
                "currency": "XTR",
                "telegram_payment_charge_id": telegram_payment_charge_id,
            }
            if attempt.status is PaymentStatus.pending:
                # successful_payment приходит только после pre-checkout, поэтому
                # попытка без сохранённой заявки — не доказательство оплаты:
                # принять её значит снова сделать инвойс многоразовым.
                if attempt.stars_pre_checkout_id is None:
                    return None
                attempt.provider_payment_id = telegram_payment_charge_id
                attempt.telegram_payment_charge_id = telegram_payment_charge_id
                attempt.status = PaymentStatus.succeeded
                attempt.verified_payload = expected_payload
                attempt.verified_at = datetime.now(UTC)
            elif attempt.status is PaymentStatus.succeeded:
                if (
                    attempt.telegram_payment_charge_id != telegram_payment_charge_id
                    or attempt.verified_payload != expected_payload
                ):
                    return None
            else:
                return None
            return attempt.id

    @staticmethod
    def _stars_invoice_payload(reference: str) -> str:
        return f"stars.{reference}"

    @staticmethod
    def _stars_invoice_reference(payload: str) -> str | None:
        prefix, separator, reference = payload.partition(".")
        if prefix != "stars" or not separator or not reference:
            return None
        if len(reference) < 32 or not all(char.isalnum() or char in "-_" for char in reference):
            return None
        return reference

    @staticmethod
    def _valid_stars_provider_id(value: str | None) -> bool:
        return isinstance(value, str) and bool(value) and len(value) <= 255

    @staticmethod
    def _stars_identity_lock_key(value: str) -> int:
        digest = sha256(f"stars:{value}".encode()).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    @staticmethod
    def _provider_key(user_id: int, client_key: str) -> str:
        """Устойчивое представление клиентского ключа, пригодное для провайдера."""
        return sha256(f"{user_id}:{client_key}".encode()).hexdigest()

    @staticmethod
    def _order_lock_key(user_id: int, client_key: str) -> int:
        """Блокировка транзакции: ещё не созданную строку заказа запереть нечем."""
        digest = sha256(f"order:{user_id}:{client_key}".encode()).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=True)

    async def finalize_success(
        self,
        attempt_id: int | None = None,
        *,
        verified_yookassa_payment: YooKassaPayment | None = None,
    ) -> FinalizationResult | None:
        """Фиксирует подтверждённую попытку и все её локальные последствия."""
        if (attempt_id is None) == (verified_yookassa_payment is None):
            msg = "нужна ровно одна ссылка на подтверждённую платёжную попытку"
            raise ValueError(msg)
        async with self._session.begin():
            if verified_yookassa_payment is None:
                order_id = await self._session.scalar(
                    select(PaymentAttempt.order_id).where(PaymentAttempt.id == attempt_id)
                )
            else:
                order_id = await self._session.scalar(
                    select(PaymentAttempt.order_id).where(
                        PaymentAttempt.provider == PaymentProvider.yookassa,
                        PaymentAttempt.provider_payment_id == verified_yookassa_payment.id,
                    )
                )
            if order_id is None:
                if verified_yookassa_payment is not None:
                    return None
                raise ServiceError("платёжная попытка не найдена", "payment_attempt_not_found")

            # Общий порядок удержания строк: order → attempt → subscription →
            # promo/voucher/referral. Первое чтение выше не блокирует строку и
            # нужно только чтобы узнать родительский order для первого lock.
            order = await self._orders.get_for_update(order_id)
            if order is None:  # pragma: no cover — FK attempt.order_id это исключает
                raise ServiceError("заказ не найден", "order_not_found")
            if attempt_id is not None:
                attempt = await self._attempts.get_for_update(attempt_id)
            else:
                assert verified_yookassa_payment is not None  # для статического сужения типа
                attempt = (
                    await self._session.execute(
                        select(PaymentAttempt)
                        .where(
                            PaymentAttempt.provider == PaymentProvider.yookassa,
                            PaymentAttempt.provider_payment_id == verified_yookassa_payment.id,
                        )
                        .with_for_update()
                    )
                ).scalar_one_or_none()
            if attempt is None or attempt.order_id != order.id:  # pragma: no cover
                raise ServiceError("платёжная попытка не найдена", "payment_attempt_not_found")

            paid_stars = self._is_recorded_stars_success(order, attempt)
            paid_yookassa = self._is_recorded_yookassa_success(order, attempt)
            if order.status is OrderStatus.expired and not (paid_stars or paid_yookassa):
                return FinalizationResult(order_id=order.id, already_finalized=False, expired=True)
            if (
                order.status is OrderStatus.pending
                and order.expires_at <= datetime.now(UTC)
                and not paid_stars
                and not paid_yookassa
            ):
                await self._expire_locked_order(order)
                return FinalizationResult(order_id=order.id, already_finalized=False, expired=True)
            if verified_yookassa_payment is not None:
                self._record_yookassa_verification(attempt, verified_yookassa_payment)
            if order.status is OrderStatus.fulfilled:
                return FinalizationResult(order_id=order.id, already_finalized=True)
            if verified_yookassa_payment is not None and (
                verified_yookassa_payment.status is not YooKassaPaymentStatus.succeeded
                or not self._yookassa_amount_matches(order, verified_yookassa_payment)
            ):
                await NotificationService(self._session).enqueue_payment_event(
                    order.id, "payment_failed"
                )
                return None
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
            existing_voucher = (
                await self._session.execute(
                    select(GiftVoucher).where(GiftVoucher.order_id == order.id).with_for_update()
                )
            ).scalar_one_or_none()
            plan = await self._plans.get(order.plan_id)
            if plan is None:  # pragma: no cover — план не удаляется физически
                raise ServiceError("тариф заказа не найден", "plan_not_found")

            if order.purpose is not OrderPurpose.gift:
                subscription = locked_subscriptions[order.user_id]
                # Резервы, погашенные до миграции 0009, снимка бонуса не имеют.
                reserved_bonus = (
                    reservation.bonus_days_snapshot if reservation is not None else None
                )
                bonus_days = max(reserved_bonus or 0, 0)
                # Снимок права описывает всю выданную длительность, включая
                # бонус: иначе будущая смена тарифа поделит остаток на
                # завышенную дневную стоимость и выдаст лишние дни.
                total_entitlement_days = order.duration_days_snapshot + bonus_days
                entitlement_days = await self._entitlement_days(order, subscription)
                event_type = self._event_type(order, subscription)
                await self._entitlements.apply_entitlement(
                    order.user_id,
                    plan,
                    entitlement_days,
                    source=SubscriptionSource.purchase,
                    event_type=event_type,
                    actor=SubscriptionActor.system,
                    origin_attempt_id=attempt.id,
                    entitlement_price_rub=order.amount_due_rub,
                    entitlement_duration_days=total_entitlement_days,
                )
                if bonus_days > 0:
                    await self._entitlements.apply_entitlement(
                        order.user_id,
                        plan,
                        bonus_days,
                        source=SubscriptionSource.purchase,
                        event_type=SubscriptionEventType.bonus_days,
                        actor=SubscriptionActor.system,
                        origin_attempt_id=None,
                        comment="бонусные дни по промокоду",
                        entitlement_price_rub=order.amount_due_rub,
                        entitlement_duration_days=total_entitlement_days,
                    )
                await self._outbox.add(TOPIC_PROVISION, {"user_id": order.user_id})
            elif existing_voucher is None:
                self._session.add(
                    GiftVoucher(
                        order_id=order.id,
                        code=token_urlsafe(18),
                        purchased_by_user_id=order.user_id,
                        expires_at=datetime.now(UTC) + timedelta(days=365),
                    )
                )

            await self._remember_card(order.user_id, attempt)

            if reservation is not None:
                await PromotionService(self._session).consume(order_id=order.id)

            # Награда начисляется только с оплаченного заказа, поэтому статус
            # ставится до её вызова. Атомарность не страдает: исключение
            # откатит и переход, и все начисления вместе с транзакцией.
            order.status = OrderStatus.fulfilled
            order.fulfilled_at = datetime.now(UTC)
            await self._stage_referral_bonus(order=order)
            await NotificationService(self._session).enqueue_payment_event(
                order.id, "payment_succeeded"
            )

        return FinalizationResult(order_id=order.id, already_finalized=False)

    async def verify_yookassa_callback(
        self, provider_payment_id: str, yookassa: YooKassaVerifier
    ) -> FinalizationResult | None:
        """Проверяет hint у YooKassa и только затем вызывает локальный финализатор.

        Сеть намеренно находится до ``session.begin()``: финализатор удерживает
        коммерческие блокировки и обязан оставаться полностью локальным.
        """
        payment = await yookassa.get_payment(provider_payment_id)
        if payment.id != provider_payment_id:
            return None
        return await self.finalize_success(verified_yookassa_payment=payment)

    async def expire_due_orders(self, *, now: datetime) -> int:
        """Закрывает просроченные заказы и освобождает их промо-резервы атомарно."""
        async with self._session.begin():
            orders = list(
                (
                    await self._session.scalars(
                        select(Order)
                        .where(
                            Order.status == OrderStatus.pending,
                            Order.expires_at <= now,
                            ~select(PaymentAttempt.id)
                            .where(
                                PaymentAttempt.order_id == Order.id,
                                PaymentAttempt.provider == PaymentProvider.stars,
                                PaymentAttempt.status == PaymentStatus.succeeded,
                            )
                            .exists(),
                        )
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for order in orders:
                await self._expire_locked_order(order)
        return len(orders)

    @staticmethod
    def _is_recorded_stars_success(order: Order, attempt: PaymentAttempt) -> bool:
        payload = attempt.verified_payload or {}
        return (
            attempt.provider is PaymentProvider.stars
            and attempt.status is PaymentStatus.succeeded
            and payload.get("currency") == "XTR"
            and payload.get("amount") == order.price_stars_snapshot
            and PaymentService._stars_charge_matches(attempt, payload)
        )

    @staticmethod
    def _stars_charge_matches(attempt: PaymentAttempt, payload: dict[str, Any]) -> bool:
        """Сверяет идентификатор списания, если попытка его знает.

        До миграции 0010 успех Stars записывался без него. Отказать такой
        строке значит забрать доступ у того, с кого Telegram уже списал звёзды:
        подтверждение оплаты уже принято, и повтор ловится не здесь, а в
        _validated_stars_attempt.
        """
        charge_id = attempt.telegram_payment_charge_id
        if charge_id is None:
            return True
        return bool(charge_id) and payload.get("telegram_payment_charge_id") == charge_id

    async def _remember_card(self, user_id: int, attempt: PaymentAttempt) -> None:
        """Сохраняет карту, если плательщик отметил галочку на форме провайдера.

        Снятая галочка ничего не отменяет: она означает «эту карту не
        запоминать», а не «отвязать прежнюю». Отвязка — только явным действием
        в кабинете.
        """
        payload = attempt.verified_payload or {}
        method_id = payload.get("payment_method_id")
        if payload.get("payment_method_saved") is not True or not isinstance(method_id, str):
            return
        title = payload.get("payment_method_title")
        await PaymentMethodService(self._session).save(
            user_id,
            provider_method_id=method_id,
            title=title if isinstance(title, str) else None,
        )

    @staticmethod
    def _is_recorded_yookassa_success(order: Order, attempt: PaymentAttempt) -> bool:
        """Пережить местный срок заказа вправе только записанный ответ провайдера."""
        payload = attempt.verified_payload or {}
        if (
            attempt.provider is not PaymentProvider.yookassa
            or attempt.status is not PaymentStatus.succeeded
            or payload.get("currency") != "RUB"
        ):
            return False
        try:
            return Decimal(str(payload.get("amount"))) == order.amount_due_rub
        except (InvalidOperation, ValueError):
            return False

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
            "payment_method_id": payment.payment_method_id,
            # Решение плательщика приходит только здесь, а финализатор работает
            # уже без сети — значит его нужно донести до него снимком.
            "payment_method_saved": payment.payment_method_saved,
            "payment_method_title": payment.payment_method_title,
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
            if (
                currency != "XTR"
                or amount != order.price_stars_snapshot
                or not self._stars_charge_matches(attempt, payload)
            ):
                raise ServiceError(
                    "сумма подтверждённой оплаты не совпадает с заказом", "payment_mismatch"
                )

    async def _entitlement_days(self, order: Order, subscription: Subscription | None) -> int:
        if subscription is None or subscription.plan_id == order.plan_id:
            return order.duration_days_snapshot
        current_price_rub = subscription.entitlement_price_rub
        current_duration_days = subscription.entitlement_duration_days
        # Миграция снимков права оставила старые строки с нулями. Запасной путь
        # только для них: право с ненулевым сроком и нулевой ценой — это
        # намеренно бесплатная выдача, оплаченного остатка у неё нет.
        if current_duration_days <= 0:
            previous_plan = await self._plans.get(subscription.plan_id)
            if previous_plan is None:  # pragma: no cover — plans are retained
                return order.duration_days_snapshot
            current_price_rub = previous_plan.price_rub
            current_duration_days = previous_plan.duration_days
        if (
            current_price_rub <= 0
            or current_duration_days <= 0
            or order.amount_due_rub <= 0
            or order.duration_days_snapshot <= 0
        ):
            return order.duration_days_snapshot
        now = datetime.now(UTC)
        carried = convert_remainder(
            expires_at=subscription.expires_at,
            now=now,
            current_price_rub=current_price_rub,
            current_duration_days=current_duration_days,
            # Прежнее удерживаемое право обменивается на саму оплаченную
            # покупку, бонусные дни добавляются следом. Снимок права ниже
            # запоминает фактически уплаченное и всю выданную длительность —
            # для будущих смен тарифа.
            new_price_rub=order.amount_due_rub,
            new_duration_days=order.duration_days_snapshot,
        )
        # apply_entitlement продлевает от expires_at. Перед этим переносим
        # именно денежный остаток старого права, затем добавляем купленный срок.
        subscription.expires_at = now + timedelta(days=carried)
        return order.duration_days_snapshot

    def _event_type(self, order: Order, subscription: Subscription | None) -> SubscriptionEventType:
        if order.purpose is OrderPurpose.renew or (
            subscription is not None and subscription.plan_id == order.plan_id
        ):
            return SubscriptionEventType.renew
        if subscription is not None:
            return SubscriptionEventType.plan_change
        return SubscriptionEventType.purchase

    async def _stage_referral_bonus(self, *, order: Order) -> None:
        """Шов для тестов восстановления; сами правила живут в ReferralService."""
        await ReferralService(self._session, self._settings).credit_for_order(order.id)
