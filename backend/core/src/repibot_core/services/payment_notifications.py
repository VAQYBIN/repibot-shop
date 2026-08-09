"""Durable payment notifications and the YooKassa recurring-payment scheduler."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    NotificationDelivery,
    Order,
    OrderPurpose,
    OrderStatus,
    PaymentAttempt,
    PaymentProvider,
    PaymentStatus,
    Plan,
    Subscription,
)
from repibot_core.db.repositories.orders import OrderRepository, PaymentAttemptRepository
from repibot_core.db.repositories.outbox import OutboxRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.yookassa.types import YooKassaPayment, YooKassaPaymentStatus
from repibot_core.settings import Settings, get_settings

# The suffix identifies the transport and makes every outbox record dispatchable
# without a second lookup.  The base is public for producers that need to route
# payment notifications without knowing their transport implementation.
TOPIC_PAYMENT_NOTIFICATION = "notify"
TOPIC_PAYMENT_EMAIL = f"{TOPIC_PAYMENT_NOTIFICATION}.email"
TOPIC_PAYMENT_TELEGRAM = f"{TOPIC_PAYMENT_NOTIFICATION}.telegram"


class YooKassaRecurringCreator(Protocol):
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

    async def get_payment(self, payment_id: str) -> YooKassaPayment: ...


class NotificationService:
    """Stages one delivery per business event and each currently available channel."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._outbox = OutboxRepository(session)

    async def enqueue_payment_event(self, order_id: int, kind: str) -> int:
        """Queue all usable destinations; retries never duplicate a delivery intent."""
        row = (
            await self._session.execute(
                select(Order.user_id, Order.plan_name_snapshot, Order.plan_code_snapshot)
                .where(Order.id == order_id)
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return 0
        user_id, plan_name, plan_code = row
        from repibot_core.db.models import User

        user = await self._session.get(User, user_id)
        if user is None:  # the order FK is cascade-protected; defensive for historical data
            return 0
        channels: list[tuple[str, str, str]] = []
        if user.telegram_id is not None:
            channels.append(("telegram", TOPIC_PAYMENT_TELEGRAM, str(user.telegram_id)))
        if user.email is not None and user.email_verified_at is not None:
            channels.append(("email", TOPIC_PAYMENT_EMAIL, user.email))

        staged = 0
        title = plan_name.get(user.language) or plan_name.get("ru") or plan_code
        for channel, topic, recipient in channels:
            delivery_id = await self._session.scalar(
                insert(NotificationDelivery)
                .values(order_id=order_id, user_id=user_id, kind=kind, channel=channel)
                .on_conflict_do_nothing(index_elements=["order_id", "kind", "channel"])
                .returning(NotificationDelivery.id)
            )
            if delivery_id is None:
                continue
            await self._outbox.add(
                topic,
                {
                    "delivery_id": delivery_id,
                    "kind": kind,
                    "language": user.language,
                    "recipient": recipient,
                    "plan": title,
                },
            )
            staged += 1
        return staged


class _LegacyAutoRenewalService:
    """Creates a stable YooKassa cycle attempt for each configured expiry offset."""

    def __init__(
        self,
        session: AsyncSession,
        yookassa: YooKassaRecurringCreator,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._yookassa = yookassa
        self._settings = settings or get_settings()
        self._orders = OrderRepository(session)
        self._attempts = PaymentAttemptRepository(session)

    async def run(self, *, now: datetime) -> int:
        """Run all due recurring attempts and return how many provider calls were made."""
        if self._session.in_transaction():
            await self._session.commit()
        subscriptions = list(
            (
                await self._session.scalars(
                    select(Subscription).where(
                        Subscription.auto_renew_enabled.is_(True),
                        Subscription.status == SubscriptionState.active,
                    )
                )
            ).all()
        )
        snapshots = [(subscription.id, subscription.expires_at) for subscription in subscriptions]
        await self._session.commit()
        calls = 0
        for subscription_id, anchor in snapshots:
            number = self._due_attempt_number(anchor, now)
            if number is None:
                continue
            if await self._run_subscription(subscription_id, anchor, number, now):
                calls += 1
        return calls

    def _due_attempt_number(self, anchor: datetime, now: datetime) -> int | None:
        due = [
            number
            for number, offset in enumerate(self._settings.auto_renew_offsets_hours, start=1)
            if anchor + timedelta(hours=offset) <= now
        ]
        return due[-1] if due else None

    @staticmethod
    def _cycle_key(subscription_id: int, anchor: datetime, number: int) -> str:
        stable_anchor = anchor.astimezone(UTC).isoformat()
        return f"auto-renew:{subscription_id}:{stable_anchor}:{number}"

    @staticmethod
    def _provider_key(cycle_key: str) -> str:
        return sha256(cycle_key.encode()).hexdigest()

    async def _run_subscription(
        self, subscription_id: int, anchor: datetime, number: int, now: datetime
    ) -> bool:
        """Claim locally, then make a provider call only after a fresh eligibility check."""
        cycle_key = self._cycle_key(subscription_id, anchor, number)
        claimed = await self._claim(subscription_id, anchor, number, cycle_key, now)
        if claimed is None:
            return False
        order, attempt, payment_method_id = claimed
        try:
            payment = await self._yookassa.create_payment(
                idempotence_key=attempt.provider_key,
                amount_rub=order.amount_due_rub,
                return_url=self._settings.public_app_url,
                description=f"Re:Pibot renewal: {order.plan_code_snapshot}",
                save_payment_method=False,
                payment_method_id=payment_method_id,
            )
        except Exception as error:
            await self._record_failure(order.id, attempt.id, number, str(error))
            return True

        # A manual renewal may have extended the subscription while the request
        # was in flight.  In that case this cycle is stale and has no entitlement
        # effect; a later cycle is based on the new expiry anchor.
        if not await self._still_current(subscription_id, anchor, order.plan_id, payment_method_id):
            return True
        if (
            payment.currency != "RUB"
            or payment.amount_rub != order.amount_due_rub
            or payment.status is not YooKassaPaymentStatus.succeeded
        ):
            await self._record_failure(order.id, attempt.id, number, "payment was not successful")
            return True

        async with self._session.begin():
            locked = await self._attempts.get_for_update(attempt.id)
            if locked is None:
                return True
            locked.provider_payment_id = payment.id
            locked.status = PaymentStatus.succeeded
            locked.verified_at = now
            locked.verified_payload = {
                "amount": format(payment.amount_rub, ".2f"),
                "currency": payment.currency,
                "status": payment.status.value,
                "payment_method_id": payment_method_id,
            }
        # Local finalization re-locks the order and remains idempotent.
        from repibot_core.services.payments import PaymentService

        await PaymentService(self._session, self._settings).finalize_success(attempt.id)
        return True

    async def _claim(
        self, subscription_id: int, anchor: datetime, number: int, cycle_key: str, now: datetime
    ) -> tuple[Order, PaymentAttempt, str] | None:
        async with self._session.begin():
            subscription = await self._session.get(
                Subscription, subscription_id, with_for_update=True
            )
            if (
                subscription is None
                or not subscription.auto_renew_enabled
                or subscription.status is not SubscriptionState.active
                or subscription.expires_at != anchor
            ):
                return None
            plan = await self._session.get(Plan, subscription.plan_id)
            if plan is None or not plan.is_active or not plan.is_visible or plan.is_trial:
                return None
            payment_method_id = await self._saved_method(subscription.user_id)
            if payment_method_id is None:
                return None
            existing = await self._session.scalar(
                select(Order).where(
                    Order.user_id == subscription.user_id, Order.client_key == cycle_key
                )
            )
            if existing is not None:
                return None
            order = await self._orders.create_pending(
                user_id=subscription.user_id,
                plan=plan,
                purpose=OrderPurpose.renew,
                client_key=cycle_key,
                expires_at=max(anchor, now) + timedelta(hours=1),
            )
            attempt = await self._attempts.get_or_create(
                order_id=order.id,
                provider=PaymentProvider.yookassa,
                attempt_no=number,
                provider_key=self._provider_key(cycle_key),
            )
            return order, attempt, payment_method_id

    async def _saved_method(self, user_id: int) -> str | None:
        attempts = list(
            (
                await self._session.scalars(
                    select(PaymentAttempt)
                    .join(Order, Order.id == PaymentAttempt.order_id)
                    .where(
                        Order.user_id == user_id,
                        PaymentAttempt.provider == PaymentProvider.yookassa,
                        PaymentAttempt.status == PaymentStatus.succeeded,
                    )
                    .order_by(PaymentAttempt.id.desc())
                )
            ).all()
        )
        for attempt in attempts:
            value = (attempt.verified_payload or {}).get("payment_method_id")
            if isinstance(value, str) and value:
                return value
        return None

    async def _still_current(
        self, subscription_id: int, anchor: datetime, plan_id: int, payment_method_id: str
    ) -> bool:
        if self._session.in_transaction():
            await self._session.commit()
        async with self._session.begin():
            subscription = await self._session.get(
                Subscription, subscription_id, with_for_update=True
            )
            if (
                subscription is None
                or not subscription.auto_renew_enabled
                or subscription.status is not SubscriptionState.active
                or subscription.expires_at != anchor
                or subscription.plan_id != plan_id
            ):
                return False
            plan = await self._session.get(Plan, plan_id)
            if plan is None or not plan.is_active or not plan.is_visible or plan.is_trial:
                return False
            return await self._saved_method(subscription.user_id) == payment_method_id

    async def _record_failure(
        self, order_id: int, attempt_id: int, number: int, error: str
    ) -> None:
        async with self._session.begin():
            attempt = await self._attempts.get_for_update(attempt_id)
            order = await self._orders.get_for_update(order_id)
            if attempt is None or order is None:
                return
            attempt.status = PaymentStatus.failed
            attempt.verified_at = datetime.now(UTC)
            attempt.verified_payload = {"error": error[:512]}
            order.status = OrderStatus.canceled
            await NotificationService(self._session).enqueue_payment_event(
                order_id, f"auto_renew_failed_{number}"
            )
            if (
                number == len(self._settings.auto_renew_offsets_hours)
                and self._settings.auto_renew_disable_after_final_failure
            ):
                subscription = await self._session.scalar(
                    select(Subscription)
                    .where(Subscription.user_id == order.user_id)
                    .with_for_update()
                )
                if subscription is not None:
                    subscription.auto_renew_enabled = False


# The first implementation above is retained in history only; this definition
# deliberately replaces it with a state machine that separates an unknown
# provider outcome from a confirmed failure.  A transport timeout is therefore
# never permission to start another renewal charge.
class AutoRenewalService:
    """Reconciles durable renewal cycles before it creates any later charge."""

    def __init__(
        self,
        session: AsyncSession,
        yookassa: YooKassaRecurringCreator,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._yookassa = yookassa
        self._settings = settings or get_settings()
        self._orders = OrderRepository(session)
        self._attempts = PaymentAttemptRepository(session)

    async def run(self, *, now: datetime) -> int:
        """Catch up cycles in order; an unresolved earlier request blocks later ones."""
        blocked: set[int] = set()
        calls = 0
        # Provider success has already been durably recorded but the process may
        # die before PaymentService finalizes it.  This worklist intentionally
        # ignores the current subscription anchor: a later manual renewal does
        # not erase the entitlement (or compensation) path for a paid charge.
        for attempt_id in await self._successful_unfulfilled_attempts():
            await self._finalize(attempt_id)
        for subscription_id, anchor, number in await self._pending_cycles():
            made_call, outcome = await self._process_cycle(
                subscription_id, anchor, number, now, allow_create=False
            )
            calls += made_call
            if outcome == "pending":
                blocked.add(subscription_id)

        for subscription_id, anchor in await self._eligible_subscriptions():
            if subscription_id in blocked:
                continue
            for number in self._due_numbers(anchor, now):
                made_call, outcome = await self._process_cycle(
                    subscription_id, anchor, number, now, allow_create=True
                )
                calls += made_call
                if outcome in {"pending", "success", "skip"}:
                    break
                if not await self._anchor_is_current(subscription_id, anchor):
                    break
        return calls

    async def _successful_unfulfilled_attempts(self) -> list[int]:
        if self._session.in_transaction():
            await self._session.commit()
        attempt_ids = list(
            (
                await self._session.scalars(
                    select(PaymentAttempt.id)
                    .join(Order, Order.id == PaymentAttempt.order_id)
                    .where(
                        Order.client_key.like("auto-renew:%"),
                        Order.status == OrderStatus.pending,
                        PaymentAttempt.provider == PaymentProvider.yookassa,
                        PaymentAttempt.status == PaymentStatus.succeeded,
                    )
                )
            ).all()
        )
        await self._session.commit()
        return attempt_ids

    async def _pending_cycles(self) -> list[tuple[int, datetime, int]]:
        if self._session.in_transaction():
            await self._session.commit()
        rows = list(
            (
                await self._session.execute(
                    select(Order.client_key)
                    .join(PaymentAttempt, PaymentAttempt.order_id == Order.id)
                    .where(
                        Order.client_key.like("auto-renew:%"),
                        Order.status == OrderStatus.pending,
                        PaymentAttempt.provider == PaymentProvider.yookassa,
                        PaymentAttempt.status == PaymentStatus.pending,
                    )
                )
            ).scalars()
        )
        await self._session.commit()
        parsed = [self._parse_cycle_key(key) for key in rows]
        cycles = (item for item in parsed if item is not None)
        return sorted(cycles, key=lambda item: (item[1], item[2]))

    async def _eligible_subscriptions(self) -> list[tuple[int, datetime]]:
        if self._session.in_transaction():
            await self._session.commit()
        subscriptions = list(
            (
                await self._session.scalars(
                    select(Subscription).where(
                        Subscription.auto_renew_enabled.is_(True),
                        Subscription.status.in_(
                            [SubscriptionState.active, SubscriptionState.expired]
                        ),
                    )
                )
            ).all()
        )
        values = [(subscription.id, subscription.expires_at) for subscription in subscriptions]
        await self._session.commit()
        return values

    def _due_numbers(self, anchor: datetime, now: datetime) -> list[int]:
        return [
            number
            for number, offset in enumerate(self._settings.auto_renew_offsets_hours, start=1)
            if anchor + timedelta(hours=offset) <= now
        ]

    @staticmethod
    def _cycle_key(subscription_id: int, anchor: datetime, number: int) -> str:
        return f"auto-renew:{subscription_id}:{anchor.astimezone(UTC).isoformat()}:{number}"

    @staticmethod
    def _parse_cycle_key(value: str) -> tuple[int, datetime, int] | None:
        parts = value.split(":", maxsplit=2)
        if len(parts) != 3 or parts[0] != "auto-renew":
            return None
        try:
            anchor, number = parts[2].rsplit(":", maxsplit=1)
            return int(parts[1]), datetime.fromisoformat(anchor), int(number)
        except ValueError:
            return None

    @staticmethod
    def _provider_key(cycle_key: str) -> str:
        return sha256(cycle_key.encode()).hexdigest()

    async def _process_cycle(
        self,
        subscription_id: int,
        anchor: datetime,
        number: int,
        now: datetime,
        *,
        allow_create: bool,
    ) -> tuple[int, str]:
        prepared = await self._prepare(subscription_id, anchor, number, now, allow_create)
        if prepared is None:
            return 0, "skip"
        order_id, attempt_id, plan_id, method_id, status = prepared
        if status is PaymentStatus.succeeded:
            await self._finalize(attempt_id)
            return 0, "success"
        if status is not PaymentStatus.pending:
            return 0, "failure"
        return await self._reconcile(
            subscription_id, anchor, number, order_id, attempt_id, plan_id, method_id
        )

    async def _prepare(
        self, subscription_id: int, anchor: datetime, number: int, now: datetime, allow_create: bool
    ) -> tuple[int, int, int, str, PaymentStatus] | None:
        cycle_key = self._cycle_key(subscription_id, anchor, number)
        async with self._session.begin():
            existing = await self._session.scalar(
                select(Order).where(Order.client_key == cycle_key).with_for_update()
            )
            if existing is not None:
                attempt = await self._session.scalar(
                    select(PaymentAttempt)
                    .where(
                        PaymentAttempt.order_id == existing.id,
                        PaymentAttempt.provider == PaymentProvider.yookassa,
                    )
                    .with_for_update()
                )
                if attempt is None:
                    return None
                method = (attempt.verified_payload or {}).get("payment_method_id")
                return (
                    existing.id,
                    attempt.id,
                    existing.plan_id,
                    method if isinstance(method, str) else "",
                    attempt.status,
                )
            if not allow_create:
                return None
            subscription = await self._session.get(
                Subscription, subscription_id, with_for_update=True
            )
            if not self._is_eligible(subscription, anchor):
                return None
            assert subscription is not None
            plan = await self._session.get(Plan, subscription.plan_id)
            if plan is None or not plan.is_active or not plan.is_visible or plan.is_trial:
                return None
            method = await self._saved_method(subscription.user_id)
            if method is None:
                return None
            order = await self._orders.create_pending(
                user_id=subscription.user_id,
                plan=plan,
                purpose=OrderPurpose.renew,
                client_key=cycle_key,
                # A provider response can be delayed.  The local order must outlive
                # the retry window so a confirmed charge always has a fulfillment path.
                expires_at=now + timedelta(days=7),
            )
            attempt = await self._attempts.get_or_create(
                order_id=order.id,
                provider=PaymentProvider.yookassa,
                attempt_no=number,
                provider_key=self._provider_key(cycle_key),
                verified_payload={"payment_method_id": method, "request_started": False},
            )
            return order.id, attempt.id, order.plan_id, method, attempt.status

    async def _reconcile(
        self,
        subscription_id: int,
        anchor: datetime,
        number: int,
        order_id: int,
        attempt_id: int,
        plan_id: int,
        method_id: str,
    ) -> tuple[int, str]:
        attempt = await self._attempt_snapshot(attempt_id)
        if attempt is None:
            return 0, "skip"
        provider_payment_id, provider_key, payload, status = attempt
        if status is PaymentStatus.succeeded:
            await self._finalize(attempt_id)
            return 0, "success"
        if status is not PaymentStatus.pending:
            return 0, "failure"

        if provider_payment_id is not None:
            try:
                payment = await self._yookassa.get_payment(provider_payment_id)
            except Exception:
                return 1, "pending"
        else:
            if not payload.get("request_started"):
                if not await self._can_charge(subscription_id, anchor, plan_id, method_id):
                    await self._abandon_unrequested(order_id, attempt_id)
                    return 0, "skip"
                await self._mark_request_started(attempt_id)
            try:
                # A replay uses the same provider key.  YooKassa therefore resolves
                # the original request instead of creating a second payment.
                payment = await self._yookassa.create_payment(
                    idempotence_key=provider_key,
                    amount_rub=await self._order_amount(order_id),
                    return_url=self._settings.public_app_url,
                    description="Re:Pibot renewal recovery",
                    save_payment_method=False,
                    payment_method_id=method_id,
                )
            except Exception:
                return 1, "pending"

        outcome = await self._record_provider_payment(attempt_id, payment)
        if outcome == "pending":
            return 1, "pending"
        if outcome == "succeeded":
            await self._finalize(attempt_id)
            return 1, "success"
        await self._record_failure(subscription_id, anchor, number, order_id, attempt_id)
        return 1, "failure"

    async def _attempt_snapshot(
        self, attempt_id: int
    ) -> tuple[str | None, str, dict[str, object], PaymentStatus] | None:
        if self._session.in_transaction():
            await self._session.commit()
        attempt = await self._session.get(PaymentAttempt, attempt_id)
        if attempt is None:
            return None
        result = (
            attempt.provider_payment_id,
            attempt.provider_key,
            dict(attempt.verified_payload or {}),
            attempt.status,
        )
        await self._session.commit()
        return result

    async def _order_amount(self, order_id: int) -> Decimal:
        if self._session.in_transaction():
            await self._session.commit()
        amount = await self._session.scalar(
            select(Order.amount_due_rub).where(Order.id == order_id)
        )
        await self._session.commit()
        assert amount is not None
        return amount

    async def _mark_request_started(self, attempt_id: int) -> None:
        async with self._session.begin():
            attempt = await self._attempts.get_for_update(attempt_id)
            if attempt is None:
                return
            payload = dict(attempt.verified_payload or {})
            payload["request_started"] = True
            attempt.verified_payload = payload

    async def _record_provider_payment(self, attempt_id: int, payment: YooKassaPayment) -> str:
        async with self._session.begin():
            attempt = await self._attempts.get_for_update(attempt_id)
            if attempt is None:
                return "pending"
            payload = dict(attempt.verified_payload or {})
            payload.update(
                {
                    "amount": format(payment.amount_rub, ".2f"),
                    "currency": payment.currency,
                    "status": payment.status.value,
                    "payment_method_id": payment.payment_method_id
                    or payload.get("payment_method_id"),
                }
            )
            attempt.provider_payment_id = payment.id
            attempt.verified_payload = payload
            attempt.verified_at = datetime.now(UTC)
            if payment.status is YooKassaPaymentStatus.succeeded:
                attempt.status = PaymentStatus.succeeded
                return "succeeded"
            if payment.status is YooKassaPaymentStatus.pending:
                attempt.status = PaymentStatus.pending
                return "pending"
            attempt.status = PaymentStatus.failed
            return "failed"

    async def _finalize(self, attempt_id: int) -> None:
        from repibot_core.services.payments import PaymentService

        await PaymentService(self._session, self._settings).finalize_success(attempt_id)

    async def _can_charge(
        self, subscription_id: int, anchor: datetime, plan_id: int, method_id: str
    ) -> bool:
        async with self._session.begin():
            subscription = await self._session.get(
                Subscription, subscription_id, with_for_update=True
            )
            if not self._is_eligible(subscription, anchor) or subscription is None:
                return False
            if subscription.plan_id != plan_id:
                return False
            plan = await self._session.get(Plan, plan_id)
            if plan is None or not plan.is_active or not plan.is_visible or plan.is_trial:
                return False
            return await self._saved_method(subscription.user_id) == method_id

    async def _abandon_unrequested(self, order_id: int, attempt_id: int) -> None:
        async with self._session.begin():
            order = await self._orders.get_for_update(order_id)
            attempt = await self._attempts.get_for_update(attempt_id)
            if order is not None:
                order.status = OrderStatus.canceled
            if attempt is not None:
                attempt.status = PaymentStatus.failed
                attempt.verified_payload = {"abandoned_stale": True}

    async def _record_failure(
        self, subscription_id: int, anchor: datetime, number: int, order_id: int, attempt_id: int
    ) -> None:
        async with self._session.begin():
            order = await self._orders.get_for_update(order_id)
            attempt = await self._attempts.get_for_update(attempt_id)
            if order is None or attempt is None:
                return
            attempt.status = PaymentStatus.failed
            order.status = OrderStatus.canceled
            subscription = await self._session.get(
                Subscription, subscription_id, with_for_update=True
            )
            if not self._is_eligible(subscription, anchor) or subscription is None:
                return
            if subscription.plan_id != order.plan_id:
                return
            await NotificationService(self._session).enqueue_payment_event(
                order_id, f"auto_renew_failed_{number}"
            )
            if (
                number == len(self._settings.auto_renew_offsets_hours)
                and self._settings.auto_renew_disable_after_final_failure
            ):
                subscription.auto_renew_enabled = False

    async def _anchor_is_current(self, subscription_id: int, anchor: datetime) -> bool:
        if self._session.in_transaction():
            await self._session.commit()
        subscription = await self._session.get(Subscription, subscription_id)
        result = self._is_eligible(subscription, anchor)
        await self._session.commit()
        return result

    @staticmethod
    def _is_eligible(subscription: Subscription | None, anchor: datetime) -> bool:
        return (
            subscription is not None
            and subscription.auto_renew_enabled
            and subscription.status in (SubscriptionState.active, SubscriptionState.expired)
            and subscription.expires_at == anchor
        )

    async def _saved_method(self, user_id: int) -> str | None:
        attempts = list(
            (
                await self._session.scalars(
                    select(PaymentAttempt)
                    .join(Order, Order.id == PaymentAttempt.order_id)
                    .where(
                        Order.user_id == user_id,
                        PaymentAttempt.provider == PaymentProvider.yookassa,
                        PaymentAttempt.status == PaymentStatus.succeeded,
                    )
                    .order_by(PaymentAttempt.id.desc())
                )
            ).all()
        )
        for attempt in attempts:
            method = (attempt.verified_payload or {}).get("payment_method_id")
            if isinstance(method, str) and method:
                return method
        return None
