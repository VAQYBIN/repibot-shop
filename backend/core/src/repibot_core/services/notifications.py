"""Единый вход уведомлений: вид события решает, куда оно уйдёт.

Раньше выбор каналов делал вызывающий, и каждое новое уведомление приходилось
учить этому заново. Здесь правило одно и записано рядом с видом события.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import NotificationDelivery, User
from repibot_core.db.repositories.outbox import OutboxRepository

# Суффикс называет транспорт, поэтому разбирающему очередь не нужен второй
# запрос, чтобы понять, куда отправлять.
TOPIC_NOTIFY = "notify"
TOPIC_NOTIFY_EMAIL = f"{TOPIC_NOTIFY}.email"
TOPIC_NOTIFY_TELEGRAM = f"{TOPIC_NOTIFY}.telegram"

# Служебные поля полезной нагрузки: они адресуют доставку, а не описывают
# событие. Обработчик обязан выкинуть их перед подстановкой в шаблон, иначе
# лишний ключ даёт KeyError на живом уведомлении.
PAYLOAD_KEYS = frozenset({"delivery_id", "kind", "language", "recipient", "user_id"})


class NotificationCategory(StrEnum):
    """Сервисное подтверждает сделку, маркетинговое — предлагает.

    Первое человек отключить не может: без него он теряет доступ молча.
    Второе — может, и это требование закона, а не удобство.
    """

    service = "service"
    marketing = "marketing"


@dataclass(frozen=True, slots=True)
class NotificationKind:
    name: str
    category: NotificationCategory
    # Префикс ключа i18n: к нему разбор очереди добавит `.bot`, `.subject`
    # или `.body`. Текст живёт в i18n, а не здесь: его переводят.
    text_key: str
    # Куда ведёт кнопка письма. Один адрес на все виды означал бы, что человек
    # с ответом поддержки попадает на страницу оплат, а с истёкшей подпиской —
    # туда же. Раздел кабинета, а не Mini App: письмо открывают в браузере,
    # где страница Mini App войти не может.
    link_path: str


_KINDS: dict[str, NotificationKind] = {
    kind.name: kind
    for kind in (
        NotificationKind(
            "payment_succeeded",
            NotificationCategory.service,
            "payment.succeeded",
            "/account/payments",
        ),
        # Подтверждённый отказ по оплате и неудача автопродления говорят
        # человеку одно и то же и различаются только поводом, поэтому текст у
        # них общий. Разными их держит ключ дедупликации, а не формулировка.
        NotificationKind(
            "payment_failed", NotificationCategory.service, "payment.failed", "/account/payments"
        ),
        NotificationKind(
            "auto_renew_failed", NotificationCategory.service, "payment.failed", "/account/payments"
        ),
        NotificationKind(
            "expiring_3",
            NotificationCategory.service,
            "subscription.expiring_3",
            "/account/subscription",
        ),
        NotificationKind(
            "expiring_1",
            NotificationCategory.service,
            "subscription.expiring_1",
            "/account/subscription",
        ),
        NotificationKind(
            "expired", NotificationCategory.service, "subscription.expired", "/account/subscription"
        ),
        NotificationKind(
            "unpaid_invoice", NotificationCategory.service, "payment.unpaid", "/account/payments"
        ),
        NotificationKind(
            "ticket_reply", NotificationCategory.service, "ticket.reply", "/account/support"
        ),
        NotificationKind("winback_1", NotificationCategory.marketing, "winback.step1", "/plans"),
        NotificationKind("winback_2", NotificationCategory.marketing, "winback.step2", "/plans"),
        NotificationKind("winback_3", NotificationCategory.marketing, "winback.step3", "/plans"),
        NotificationKind("winback_4", NotificationCategory.marketing, "winback.step4", "/plans"),
    )
}

# Номер попытки автопродления входит в вид, потому что дедуплицирует доставку,
# но текст и категория у всех попыток общие.
_NUMBERED_PREFIX = "auto_renew_failed_"


def all_kinds() -> tuple[NotificationKind, ...]:
    """Все объявленные виды. Нужен проверке, что у каждого есть тексты."""
    return tuple(_KINDS.values())


def resolve_kind(kind: str) -> NotificationKind:
    """Вид события по его имени; неизвестное имя — ошибка сборки, а не тишина."""
    if kind.startswith(_NUMBERED_PREFIX):
        return _KINDS["auto_renew_failed"]
    found = _KINDS.get(kind)
    if found is None:
        msg = f"неизвестный вид уведомления: {kind}"
        raise KeyError(msg)
    return found


class NotificationService:
    """Ставит доставки по правилу категории; повтор ключа ничего не добавляет."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._outbox = OutboxRepository(session)

    async def enqueue(
        self,
        *,
        user_id: int,
        kind: str,
        dedup_key: str,
        params: dict[str, Any],
        order_id: int | None = None,
    ) -> int:
        user = await self._session.get(User, user_id)
        if user is None:
            return 0
        channels = self._channels(user, resolve_kind(kind))

        staged = 0
        for channel, topic, recipient in channels:
            delivery_id = await self._session.scalar(
                insert(NotificationDelivery)
                .values(
                    order_id=order_id,
                    user_id=user_id,
                    kind=kind,
                    channel=channel,
                    dedup_key=dedup_key,
                )
                .on_conflict_do_nothing(index_elements=["dedup_key", "channel"])
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
                    # Нужен ссылке отписки в письме: собрать её из адресата
                    # нельзя, токен подписывается по идентификатору.
                    "user_id": user_id,
                    **params,
                },
            )
            staged += 1
        return staged

    @staticmethod
    def _channels(user: User, kind: NotificationKind) -> list[tuple[str, str, str]]:
        """Привязанные каналы в порядке предпочтения.

        Маркетинг берёт первый: Telegram живее и дешевле почты, и человек
        читает его чаще. Сервисное берёт все: письмо остаётся чеком.
        """
        available: list[tuple[str, str, str]] = []
        if user.telegram_id is not None:
            available.append(("telegram", TOPIC_NOTIFY_TELEGRAM, str(user.telegram_id)))
        if user.email is not None and user.email_verified_at is not None:
            available.append(("email", TOPIC_NOTIFY_EMAIL, user.email))
        if kind.category is NotificationCategory.service:
            return available
        if user.marketing_opt_out_at is not None:
            return []
        return available[:1]

    async def enqueue_payment_event(self, order_id: int, kind: str) -> int:
        """Совместимость с денежным контуром: тот же вход, ключ по заказу."""
        from repibot_core.db.models import Order

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
        user = await self._session.get(User, user_id)
        if user is None:  # внешний ключ заказа это исключает; защита от старых данных
            return 0
        title = plan_name.get(user.language) or plan_name.get("ru") or plan_code
        return await self.enqueue(
            user_id=user_id,
            kind=kind,
            dedup_key=f"order:{order_id}:{kind}",
            params={"plan": title},
            order_id=order_id,
        )
