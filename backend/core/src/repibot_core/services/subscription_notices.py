"""Напоминания о судьбе подписки.

Ключ дедупликации несёт дату окончания. Это единственное, что делает крон
безопасным при любом расписании: продление сдвигает дату и честно открывает
новый цикл, а повторный запуск в том же цикле не порождает второго письма.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Order, OrderStatus, Plan, Subscription
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.notifications import NotificationService
from repibot_core.services.payment_methods import PaymentMethodService
from repibot_core.settings import Settings, get_settings

# Насколько давно подписка могла кончиться, чтобы об этом ещё стоило
# сообщать. Статус проставляет отдельный крон раз в час; двое суток —
# запас на его простой и не более того.
EXPIRED_NOTICE_WINDOW = timedelta(days=2)


class SubscriptionNoticeService:
    """Собирает поводы напомнить и ставит их в очередь.

    Отправкой занимается разбор очереди: здесь нет ни Telegram, ни SMTP,
    поэтому прогон крона не зависит от того, отвечает ли сейчас транспорт.
    """

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._notifications = NotificationService(session)

    async def run(self, *, now: datetime) -> int:
        """Ставит все поводы разом и возвращает число поставленных доставок."""
        staged = 0
        staged += await self._expiring(now)
        staged += await self._expired(now)
        staged += await self._unpaid(now)
        return staged

    async def _expiring(self, now: datetime) -> int:
        staged = 0
        # Порог, за который подписка уже отвечает: пороги перебираются от
        # срочного к дальнему, и первый подошедший забирает подписку себе.
        # Иначе тому, у кого остался день, вслед за «завтра» уходило бы ещё и
        # «через три дня» — человек поверит второму и потеряет доступ.
        claimed: set[int] = set()
        for days in sorted(self._settings.expiry_reminder_days):
            border = now + timedelta(days=days)
            rows = (
                await self._session.execute(
                    select(Subscription, Plan.name)
                    .join(Plan, Plan.id == Subscription.plan_id)
                    .where(
                        Subscription.status == SubscriptionState.active,
                        Subscription.expires_at > now,
                        Subscription.expires_at <= border,
                    )
                )
            ).all()
            for subscription, plan_name in rows:
                if subscription.id in claimed:
                    continue
                claimed.add(subscription.id)
                if await self._renews_itself(subscription):
                    continue
                staged += await self._stage(
                    subscription,
                    plan_name,
                    kind=f"expiring_{days}",
                    dedup_key=(
                        f"sub:{subscription.id}:expiring:{days}:"
                        f"{subscription.expires_at.astimezone(UTC).isoformat()}"
                    ),
                )
        return staged

    async def _expired(self, now: datetime) -> int:
        """Подписка, у которой доступ только что отключён.

        Окно обязательно. Ключ дедупликации спасает от повторов, но не от
        первого раза: без окна выкатка этой задачи стала бы рассылкой «Подписка
        закончилась» каждому, кто отвалился хоть год назад. Заодно это
        ежечасный полный проход по таблице, которая только растёт.

        Двое суток, а не час: статус проставляет отдельный крон, идущий раз в
        час, и запас нужен на его простой. Всё, что старше, — уже не новость,
        а повод для лесенки возврата, и это другая задача.
        """
        rows = (
            await self._session.execute(
                select(Subscription, Plan.name)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(
                    Subscription.status == SubscriptionState.expired,
                    Subscription.expires_at > now - EXPIRED_NOTICE_WINDOW,
                )
            )
        ).all()
        staged = 0
        for subscription, plan_name in rows:
            staged += await self._stage(
                subscription,
                plan_name,
                kind="expired",
                dedup_key=(
                    f"sub:{subscription.id}:expired:"
                    f"{subscription.expires_at.astimezone(UTC).isoformat()}"
                ),
            )
        return staged

    async def _unpaid(self, now: datetime) -> int:
        """Заказ, зависший в pending: человек начал оплату и не закончил.

        Срок оплаты проверяется отдельно от возраста: напоминать про счёт,
        который через минуту протухнет, значит звать туда, где уже нельзя
        заплатить.
        """
        border = now - timedelta(minutes=self._settings.unpaid_invoice_after_minutes)
        rows = (
            await self._session.execute(
                select(Order).where(
                    Order.status == OrderStatus.pending,
                    Order.created_at <= border,
                    Order.expires_at > now,
                )
            )
        ).scalars()
        staged = 0
        # Кабинет, а не Mini App: эта же строка уходит в письмо, а страница
        # Mini App вне Telegram войти не может. rstrip нужен потому, что в
        # .env адрес пишут и со слешом на конце, а «//account» не откроется.
        link = f"{self._settings.public_web_url.rstrip('/')}/account/payments"
        for order in rows:
            title = (
                order.plan_name_snapshot.get("ru")
                or next(iter(order.plan_name_snapshot.values()), "")
                or order.plan_code_snapshot
            )
            staged += await self._notifications.enqueue(
                user_id=order.user_id,
                kind="unpaid_invoice",
                dedup_key=f"order:{order.id}:unpaid",
                params={"plan": title, "link": link},
                order_id=order.id,
            )
        return staged

    async def _renews_itself(self, subscription: Subscription) -> bool:
        """Включённая настройка без карты — это не автопродление, а надежда."""
        if not subscription.auto_renew_enabled:
            return False
        method = await PaymentMethodService(self._session).current_method_id(subscription.user_id)
        return method is not None

    async def _stage(
        self, subscription: Subscription, plan_name: dict[str, str], *, kind: str, dedup_key: str
    ) -> int:
        # Название тарифа берётся по-русски, а язык сообщения — из профиля.
        # Осознанное упрощение того же вида, что принято в
        # NotificationService.enqueue_payment_event, где имя берётся снимком.
        title = plan_name.get("ru") or next(iter(plan_name.values()), "")
        return await self._notifications.enqueue(
            user_id=subscription.user_id,
            kind=kind,
            dedup_key=dedup_key,
            params={
                "plan": title,
                "date": subscription.expires_at.astimezone(UTC).strftime("%d.%m.%Y"),
            },
        )
