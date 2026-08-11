"""Промокоды и подарки; все изменения прав происходят под блокировками БД."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    GiftVoucher,
    Order,
    OrderPurpose,
    PromoCode,
    PromoReservation,
    SubscriptionActor,
    SubscriptionEventType,
    SubscriptionSource,
)
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.services.errors import ServiceError
from repibot_core.services.provisioning import TOPIC_PROVISION
from repibot_core.services.subscriptions import SubscriptionService, SubscriptionView
from repibot_core.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class PromotionInput:
    code: str
    percent_off: int = 0
    bonus_days: int = 0
    max_uses: int | None = None
    per_user_limit: int | None = None
    is_active: bool = True
    starts_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PromotionQuote:
    promo_id: int
    code: str
    discount_rub: Decimal
    bonus_days: int


@dataclass(frozen=True, slots=True)
class GiftVoucherView:
    code: str
    purchased_at: datetime
    redeemed_at: datetime | None
    expires_at: datetime
    purchased_by_me: bool
    redeemed_by_me: bool


class PromotionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: PromotionInput) -> PromoCode:
        code = data.code.strip().upper()
        if not code or (data.percent_off == 0 and data.bonus_days == 0):
            raise ServiceError("промокод должен давать скидку или дни", "validation_error")
        promo = PromoCode(
            code=code,
            percent_off=data.percent_off,
            bonus_days=data.bonus_days,
            max_uses=data.max_uses,
            per_user_limit=data.per_user_limit,
            is_active=data.is_active,
            starts_at=data.starts_at,
            expires_at=data.expires_at,
        )
        self._session.add(promo)
        await self._session.flush()
        return promo

    async def list(self) -> list[PromoCode]:
        return list((await self._session.scalars(select(PromoCode).order_by(PromoCode.id))).all())

    async def update(self, promo_id: int, data: PromotionInput) -> PromoCode:
        promo = await self._session.get(PromoCode, promo_id, with_for_update=True)
        if promo is None:
            raise ServiceError("промокод не найден", "not_found")
        code = data.code.strip().upper()
        if not code or (data.percent_off == 0 and data.bonus_days == 0):
            raise ServiceError("промокод должен давать скидку или дни", "validation_error")
        promo.code, promo.percent_off, promo.bonus_days = code, data.percent_off, data.bonus_days
        promo.max_uses, promo.per_user_limit, promo.is_active = (
            data.max_uses,
            data.per_user_limit,
            data.is_active,
        )
        promo.starts_at, promo.expires_at = data.starts_at, data.expires_at
        return promo

    async def deactivate(self, promo_id: int) -> None:
        promo = await self._session.get(PromoCode, promo_id, with_for_update=True)
        if promo is None:
            raise ServiceError("промокод не найден", "not_found")
        promo.is_active = False

    async def prepare(self, *, user_id: int, code: str, gross_rub: Decimal) -> PromotionQuote:
        promo = await self._locked_available(code)
        await self._assert_limits(promo, user_id)
        discount = (gross_rub * Decimal(promo.percent_off) / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return PromotionQuote(promo.id, promo.code, discount, promo.bonus_days)

    async def reserve(self, *, order: Order, user_id: int, code: str) -> PromotionQuote:
        """Резервирует код под уже созданный снимок заказа; нужен и путям восстановления."""
        if order.purpose not in (OrderPurpose.purchase, OrderPurpose.renew):
            raise ServiceError("промокод недоступен", "promo_unavailable")
        quote = await self.prepare(user_id=user_id, code=code, gross_rub=order.gross_rub)
        await self.reserve_prepared(order=order, user_id=user_id, quote=quote)
        return quote

    async def reserve_prepared(self, *, order: Order, user_id: int, quote: PromotionQuote) -> None:
        existing = await self._session.scalar(
            select(PromoReservation).where(PromoReservation.order_id == order.id)
        )
        if existing is not None:
            return
        self._session.add(
            PromoReservation(
                order_id=order.id,
                promo_code_id=quote.promo_id,
                user_id=user_id,
                bonus_days_snapshot=quote.bonus_days,
                expires_at=order.expires_at,
            )
        )
        await self._session.flush()

    async def consume(self, *, order_id: int) -> int:
        reservation = (
            await self._session.execute(
                select(PromoReservation)
                .where(PromoReservation.order_id == order_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if reservation is None or reservation.consumed_at is not None:
            return 0
        reservation.consumed_at = datetime.now(UTC)
        return reservation.promo_code_id

    async def release_expired(self, *, now: datetime) -> int:
        result = await self._session.execute(
            delete(PromoReservation)
            .where(PromoReservation.consumed_at.is_(None), PromoReservation.expires_at <= now)
            .returning(PromoReservation.id)
        )
        return len(result.scalars().all())

    async def _locked_available(self, code: str) -> PromoCode:
        now = datetime.now(UTC)
        promo = (
            await self._session.execute(
                select(PromoCode).where(PromoCode.code == code.strip().upper()).with_for_update()
            )
        ).scalar_one_or_none()
        if (
            promo is None
            or not promo.is_active
            or (promo.starts_at is not None and promo.starts_at > now)
            or (promo.expires_at is not None and promo.expires_at <= now)
        ):
            raise ServiceError("промокод недоступен", "promo_unavailable")
        return promo

    async def _assert_limits(self, promo: PromoCode, user_id: int) -> None:
        active = PromoReservation.consumed_at.is_not(None) | (
            PromoReservation.expires_at > datetime.now(UTC)
        )
        if promo.max_uses is not None:
            used = await self._session.scalar(
                select(func.count())
                .select_from(PromoReservation)
                .where(PromoReservation.promo_code_id == promo.id, active)
            )
            if int(used or 0) >= promo.max_uses:
                raise ServiceError("промокод недоступен", "promo_unavailable")
        if promo.per_user_limit is not None:
            used_by_user = await self._session.scalar(
                select(func.count())
                .select_from(PromoReservation)
                .where(
                    PromoReservation.promo_code_id == promo.id,
                    PromoReservation.user_id == user_id,
                    active,
                )
            )
            if int(used_by_user or 0) >= promo.per_user_limit:
                raise ServiceError("промокод недоступен", "promo_unavailable")


class GiftService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session, self._settings = session, settings or get_settings()
        self._plans, self._subscriptions = PlanRepository(session), SubscriptionRepository(session)
        self._outbox = OutboxRepository(session)
        self._entitlements = SubscriptionService(session, self._settings, provisioning=None)

    async def redeem(self, code: str, recipient_user_id: int) -> SubscriptionView:
        if self._session.in_transaction():
            await self._session.commit()
        async with self._session.begin():
            # Порядок замков общий для всех путей: заказ, подписка, ваучер.
            # Начать с ваучера значит встретиться с финализацией в обратном
            # порядке — один держит заказ и ждёт ваучер, другой наоборот, — и
            # разойтись через deadlock: оплаченный подарок не дойдёт до
            # получателя. Код и заказ ваучера читаются без замка: они не
            # меняются, а состояние проверяется ниже, уже под замком.
            found = (
                await self._session.execute(
                    select(GiftVoucher.id, GiftVoucher.order_id).where(
                        GiftVoucher.code == code.strip()
                    )
                )
            ).one_or_none()
            if found is None:
                raise ServiceError("ваучер не найден", "not_found")
            voucher_id, voucher_order_id = found
            now = datetime.now(UTC)
            order = await self._session.get(Order, voucher_order_id, with_for_update=True)
            if order is None or order.purpose is not OrderPurpose.gift:
                raise ServiceError("ваучер недоступен", "gift_unavailable")
            plan = await self._plans.get(order.plan_id)
            if plan is None:
                raise ServiceError("тариф подарка не найден", "plan_not_found")
            await self._subscriptions.lock_user_for_entitlement(recipient_user_id)
            current = await self._subscriptions.get_for_user_for_update(recipient_user_id)
            voucher = await self._session.get(GiftVoucher, voucher_id, with_for_update=True)
            if voucher is None:  # pragma: no cover — строку выше уже нашли по коду
                raise ServiceError("ваучер не найден", "not_found")
            if voucher.redeemed_at is not None or voucher.expires_at <= now:
                raise ServiceError("ваучер уже недоступен", "gift_unavailable")
            target, days = plan, order.duration_days_snapshot
            if current is not None and current.plan_id != plan.id and current.expires_at > now:
                current_plan = await self._plans.get(current.plan_id)
                if current_plan is not None and current.entitlement_price_rub > 0:
                    target = current_plan
                    days = int(
                        Decimal(order.price_rub_snapshot)
                        * Decimal(current.entitlement_duration_days)
                        / current.entitlement_price_rub
                    )
            applied = await self._entitlements.apply_entitlement(
                recipient_user_id,
                target,
                max(days, 1),
                source=SubscriptionSource.gift,
                event_type=SubscriptionEventType.gift,
                actor=SubscriptionActor.system,
                origin_attempt_id=None,
            )
            voucher.redeemed_by_user_id, voucher.redeemed_at = recipient_user_id, now
            await self._outbox.add(TOPIC_PROVISION, {"user_id": recipient_user_id})
        return SubscriptionView(
            plan_code=target.code,
            plan_name=target.name,
            status=applied.status,
            started_at=applied.started_at,
            expires_at=applied.expires_at,
            subscription_url=None,
            traffic_limit_bytes=target.traffic_limit_bytes,
            hwid_device_limit=target.hwid_device_limit,
            is_trial=target.is_trial,
            auto_renew_enabled=applied.auto_renew_enabled,
        )

    async def list_for_user(self, user_id: int) -> list[GiftVoucherView]:
        rows = list(
            (
                await self._session.execute(
                    select(GiftVoucher)
                    .where(
                        or_(
                            GiftVoucher.purchased_by_user_id == user_id,
                            GiftVoucher.redeemed_by_user_id == user_id,
                        )
                    )
                    .order_by(GiftVoucher.created_at.desc())
                )
            ).scalars()
        )
        return [
            GiftVoucherView(
                v.code,
                v.created_at,
                v.redeemed_at,
                v.expires_at,
                v.purchased_by_user_id == user_id,
                v.redeemed_by_user_id == user_id,
            )
            for v in rows
        ]
