# Слой доставки и согласие Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Уведомление можно поставить по любому поводу, а не только по заказу;
категория события решает, в какие каналы оно уйдёт; человек может отказаться от
маркетинга одной кнопкой; очередь перестаёт упираться в 1200 сообщений в час.

**Architecture:** `notification_deliveries` дедуплицирует по произвольному
`dedup_key`, а `order_id` становится необязательным следом для денежных
событий. Новый модуль `services/notifications.py` держит реестр видов
уведомлений: у каждого вида есть категория и префикс ключа i18n. Категория
`service` уходит во все привязанные каналы, `marketing` — в один и только
несогласившимся отказ. `OutboxDispatcher` отправляет пачку параллельно, а
запись результатов остаётся последовательной — одна сессия SQLAlchemy не
переживает одновременных запросов.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async/PostgreSQL 18, Alembic,
TaskIQ/Valkey, aiogram 3, React 19, Next.js 16, TanStack Query v5, TanStack
Router, Vitest.

## Global Constraints

- Дедупликация — по паре `(dedup_key, channel)`. Формы ключей заданы
  спецификацией: `order:{order_id}:{kind}`,
  `sub:{subscription_id}:expiring:{days}:{expires_at}`,
  `sub:{subscription_id}:expired:{expires_at}`, `order:{order_id}:unpaid`,
  `winback:{user_id}:step{n}:{expired_at}`, `ticket:{ticket_id}:msg:{message_id}`.
- Категория `service` — все привязанные и подтверждённые каналы, отключить
  нельзя. Категория `marketing` — один канал: Telegram, если привязан, иначе
  подтверждённая почта; уходит только тем, у кого `marketing_opt_out_at IS NULL`.
- Отсутствие канала — не ошибка: строки доставки не создаются, очередь не
  копит сообщения в никуда.
- Токен отписки подписан `JWT_SECRET`, несёт только идентификатор пользователя
  и тип `unsubscribe`, и не годится ни для чего другого.
- Все комментарии и докстринги на русском и объясняют «почему».
- Каждая задача: сначала падающий тест, обязательно запущенный и увиденный
  красным, затем минимальная реализация, затем тематический commit на ветке
  `dev`. Полный `uv run check` — перед сдачей плана.
- Строки не длиннее 100 символов (ruff), переводы строк LF.

---

### Task 1: Дедупликация без заказа

**Files:**
- Modify: `backend/core/src/repibot_core/db/models/commerce.py:275-291`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0014_delivery_dedup_key.py`
- Modify: `backend/core/tests/test_payment_notifications.py`

**Interfaces:**
- Produces `NotificationDelivery.dedup_key: str`, `NotificationDelivery.order_id: int | None`,
  ограничение `uq_notification_deliveries_dedup` на `(dedup_key, channel)`.
- Consumes существующую `NotificationDelivery` и голову миграций `0013`.

- [ ] **Step 1: Падающий тест — доставка без заказа**

Добавить в `backend/core/tests/test_payment_notifications.py`:

```python
async def test_delivery_exists_without_an_order(db_session: AsyncSession) -> None:
    """Ни одно уведомление подпроекта 4 не связано с заказом.

    Обязательный order_id означал бы, что напоминание об истечении нужно
    привязывать к выдуманному заказу — и первый же отчёт по деньгам стал бы
    врать.
    """
    user = User(email=None, telegram_id=100_777, referral_code="freekey1")
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        NotificationDelivery(
            user_id=user.id, kind="expiring_3", channel="telegram", dedup_key="sub:1:expiring:3:x"
        )
    )
    await db_session.commit()

    stored = await db_session.scalar(select(NotificationDelivery))
    assert stored is not None
    assert stored.order_id is None
    assert stored.dedup_key == "sub:1:expiring:3:x"
```

- [ ] **Step 2: Второй падающий тест — ключ дедуплицирует**

```python
async def test_same_key_and_channel_cannot_be_staged_twice(db_session: AsyncSession) -> None:
    """Повторный запуск крона не должен слать второе напоминание."""
    user = User(email=None, telegram_id=100_778, referral_code="freekey2")
    db_session.add(user)
    await db_session.flush()
    for _ in range(2):
        db_session.add(
            NotificationDelivery(
                user_id=user.id, kind="expired", channel="email", dedup_key="sub:2:expired:x"
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.commit()
```

Импорт: `from sqlalchemy.exc import IntegrityError`.

- [ ] **Step 3: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_payment_notifications.py -k "without_an_order or staged_twice" -q`
Expected: FAIL — `null value in column "order_id"` и отсутствие `dedup_key`.

- [ ] **Step 4: Поменять модель**

В `commerce.py` заменить объявление на:

```python
class NotificationDelivery(Base):
    """Дедуплицированное намерение отправить уведомление.

    Ключ произвольный, потому что поводов больше, чем заказов: напоминание об
    истечении привязано к дате окончания, ступень лесенки — к пользователю и
    номеру, ответ поддержки — к сообщению.
    """

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("dedup_key", "channel", name="uq_notification_deliveries_dedup"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Денежный след там, где он есть. Для истечения и рассылки заказа нет.
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    dedup_key: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
```

- [ ] **Step 5: Миграция**

`0014_delivery_dedup_key.py`:

```python
"""Ключ дедупликации вместо заказа.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column("dedup_key", sa.String(length=160), nullable=True),
    )
    # Существующие строки все до одной про заказ: восстанавливаем ту же форму
    # ключа, которую с этого момента собирает сервис.
    op.execute("update notification_deliveries set dedup_key = 'order:' || order_id || ':' || kind")
    op.alter_column("notification_deliveries", "dedup_key", nullable=False)
    op.alter_column("notification_deliveries", "order_id", nullable=True)
    op.drop_constraint("uq_notification_deliveries_dedup", "notification_deliveries")
    op.create_unique_constraint(
        "uq_notification_deliveries_dedup", "notification_deliveries", ["dedup_key", "channel"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_notification_deliveries_dedup", "notification_deliveries")
    op.execute("delete from notification_deliveries where order_id is null")
    op.alter_column("notification_deliveries", "order_id", nullable=False)
    op.create_unique_constraint(
        "uq_notification_deliveries_dedup",
        "notification_deliveries",
        ["order_id", "kind", "channel"],
    )
    op.drop_column("notification_deliveries", "dedup_key")
```

- [ ] **Step 6: Научить сервис ставить ключ**

В `backend/core/src/repibot_core/services/payment_notifications.py`, в теле цикла
`for channel, topic, recipient in channels:` добавить `dedup_key` в `insert(...)`
и поменять цель конфликта:

```python
            delivery_id = await self._session.scalar(
                insert(NotificationDelivery)
                .values(
                    order_id=order_id,
                    user_id=user_id,
                    kind=kind,
                    channel=channel,
                    dedup_key=f"order:{order_id}:{kind}",
                )
                .on_conflict_do_nothing(index_elements=["dedup_key", "channel"])
                .returning(NotificationDelivery.id)
            )
```

- [ ] **Step 7: Прогнать набор**

Run: `uv run pytest backend/core/tests/test_payment_notifications.py backend/core/tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/core/src/repibot_core/db/models/commerce.py \
        backend/core/src/repibot_core/db/migrations/versions/0014_delivery_dedup_key.py \
        backend/core/src/repibot_core/services/payment_notifications.py \
        backend/core/tests/test_payment_notifications.py
git commit -m "feat: дедуплицировать уведомления по ключу, а не по заказу"
```

---

### Task 2: Реестр видов и выбор канала

**Files:**
- Create: `backend/core/src/repibot_core/services/notifications.py`
- Modify: `backend/core/src/repibot_core/services/payment_notifications.py`
- Modify: `backend/core/src/repibot_core/services/dispatcher.py:39-56`
- Create: `backend/core/tests/test_notifications.py`

**Interfaces:**
- Produces `NotificationCategory` (`service`, `marketing`), `NotificationKind(name, category, text_key)`,
  `resolve_kind(kind: str) -> NotificationKind`, `TOPIC_NOTIFY_EMAIL`, `TOPIC_NOTIFY_TELEGRAM`,
  `NotificationService.enqueue(*, user_id, kind, dedup_key, params, order_id=None) -> int`.
- Consumes `NotificationDelivery.dedup_key` из задачи 1.
- `payment_notifications.NotificationService` остаётся тем же именем и продолжает
  работать: он импортируется из нового модуля.

- [ ] **Step 1: Падающий тест — категория решает каналы**

`backend/core/tests/test_notifications.py`:

```python
"""Категория события решает, куда оно уйдёт."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import NotificationDelivery, OutboxMessage, User
from repibot_core.services.notifications import NotificationService

pytestmark = pytest.mark.docker


async def _user(session: AsyncSession, *, telegram: bool, verified_email: bool) -> User:
    user = User(
        email="both@example.org" if verified_email else None,
        email_verified_at=datetime.now(UTC) if verified_email else None,
        telegram_id=100_501 if telegram else None,
        referral_code="notify01",
    )
    session.add(user)
    await session.flush()
    return user


async def test_service_event_reaches_every_linked_channel(db_session: AsyncSession) -> None:
    """Чек об оплате остаётся человеку письмом, даже если он живёт в Telegram."""
    user = await _user(db_session, telegram=True, verified_email=True)

    staged = await NotificationService(db_session).enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:1:expired:x", params={"plan": "Месяц"}
    )
    await db_session.commit()

    topics = sorted((await db_session.scalars(select(OutboxMessage.topic))).all())
    assert staged == 2
    assert topics == ["notify.email", "notify.telegram"]


async def test_marketing_event_takes_one_channel_preferring_telegram(
    db_session: AsyncSession,
) -> None:
    """Одно и то же предложение дважды — прямой путь к отписке."""
    user = await _user(db_session, telegram=True, verified_email=True)

    await NotificationService(db_session).enqueue(
        user_id=user.id, kind="winback_1", dedup_key="winback:1:step1:x", params={}
    )
    await db_session.commit()

    assert list((await db_session.scalars(select(OutboxMessage.topic))).all()) == ["notify.telegram"]


async def test_marketing_event_falls_back_to_verified_email(db_session: AsyncSession) -> None:
    user = await _user(db_session, telegram=False, verified_email=True)

    await NotificationService(db_session).enqueue(
        user_id=user.id, kind="winback_1", dedup_key="winback:2:step1:x", params={}
    )
    await db_session.commit()

    assert list((await db_session.scalars(select(OutboxMessage.topic))).all()) == ["notify.email"]


async def test_no_channel_is_not_an_error(db_session: AsyncSession) -> None:
    """Очередь не должна копить сообщения в никуда."""
    user = await _user(db_session, telegram=False, verified_email=False)

    staged = await NotificationService(db_session).enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:3:expired:x", params={}
    )
    await db_session.commit()

    assert staged == 0
    assert (await db_session.scalars(select(NotificationDelivery))).all() == []


async def test_same_key_is_staged_once(db_session: AsyncSession) -> None:
    user = await _user(db_session, telegram=True, verified_email=False)
    service = NotificationService(db_session)

    first = await service.enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:4:expired:x", params={}
    )
    second = await service.enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:4:expired:x", params={}
    )
    await db_session.commit()

    assert (first, second) == (1, 0)
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_notifications.py -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.services.notifications`.

- [ ] **Step 3: Написать модуль**

`backend/core/src/repibot_core/services/notifications.py`:

```python
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


_KINDS: dict[str, NotificationKind] = {
    kind.name: kind
    for kind in (
        NotificationKind("payment_succeeded", NotificationCategory.service, "payment.succeeded"),
        NotificationKind("auto_renew_failed", NotificationCategory.service, "payment.failed"),
        NotificationKind("expiring_3", NotificationCategory.service, "subscription.expiring_3"),
        NotificationKind("expiring_1", NotificationCategory.service, "subscription.expiring_1"),
        NotificationKind("expired", NotificationCategory.service, "subscription.expired"),
        NotificationKind("unpaid_invoice", NotificationCategory.service, "payment.unpaid"),
        NotificationKind("ticket_reply", NotificationCategory.service, "ticket.reply"),
        NotificationKind("winback_1", NotificationCategory.marketing, "winback.step1"),
        NotificationKind("winback_2", NotificationCategory.marketing, "winback.step2"),
        NotificationKind("winback_3", NotificationCategory.marketing, "winback.step3"),
        NotificationKind("winback_4", NotificationCategory.marketing, "winback.step4"),
    )
}

# Номер попытки автопродления входит в вид, потому что дедуплицирует доставку,
# но текст и категория у всех попыток общие.
_NUMBERED_PREFIX = "auto_renew_failed_"


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
```

- [ ] **Step 4: Убрать дубликат из денежного модуля**

В `payment_notifications.py` удалить класс `NotificationService` целиком и
заменить объявления тем, что теперь живёт в новом модуле:

```python
from repibot_core.services.notifications import (
    TOPIC_NOTIFY,
    TOPIC_NOTIFY_EMAIL,
    TOPIC_NOTIFY_TELEGRAM,
    NotificationService,
)

# Прежние имена сохраняются: их знает денежный контур и его тесты.
TOPIC_PAYMENT_NOTIFICATION = TOPIC_NOTIFY
TOPIC_PAYMENT_EMAIL = TOPIC_NOTIFY_EMAIL
TOPIC_PAYMENT_TELEGRAM = TOPIC_NOTIFY_TELEGRAM
```

Удалить из файла ставшие лишними импорты `NotificationDelivery`, `insert` и
`User`, если они больше нигде не используются.

- [ ] **Step 5: Разбор очереди берёт текст по виду**

В `dispatcher.py` заменить тело `handle_payment_telegram` (переименовав его в
`handle_notify_telegram`) и регистрацию темы:

```python
    async def handle_notify_telegram(payload: dict[str, object]) -> None:
        language = str(payload["language"])
        kind = resolve_kind(str(payload["kind"]))
        # Служебные поля не попадают в текст: translate подставляет всё, что
        # получил, и лишний ключ в шаблоне даёт KeyError на живом уведомлении.
        params = {
            key: value
            for key, value in payload.items()
            if key not in {"delivery_id", "kind", "language", "recipient", "user_id"}
        }
        text = translate(language, f"{kind.text_key}.bot", **params)
        recipient = int(str(payload["recipient"]))
        if telegram is None:
            # Клиент живёт столько же, сколько прогон задачи, и собирается
            # вызывающим: соединение с Valkey и http-клиент на каждое
            # сообщение — это плата за каждое уведомление, а разбор очереди
            # берёт до сотни сообщений за раз. Сообщение вернётся в очередь и
            # уйдёт следующим прогоном, уже с клиентом.
            msg = "клиент бота не передан диспетчеру"
            raise RuntimeError(msg)
        await telegram.send_message(recipient, text)

    dispatcher.register(TOPIC_NOTIFY_TELEGRAM, handle_notify_telegram)
```

Импорт: `from repibot_core.services.notifications import TOPIC_NOTIFY_TELEGRAM, resolve_kind`.
Импорт `TOPIC_PAYMENT_TELEGRAM` из `payment_notifications` удалить.

- [ ] **Step 6: То же для почты**

Открыть `backend/core/src/repibot_core/services/email_dispatch.py`, найти
обработчик темы `notify.email` и заменить сборку темы и тела письма на
`resolve_kind`: `translate(language, f"{kind.text_key}.subject", **params)` и
`translate(language, f"{kind.text_key}.body", **params)`, где `params` собирается
тем же способом, что и в задаче выше. Если обработчик собирает текст по
условию `kind == "payment_succeeded"`, это условие удаляется целиком.

- [ ] **Step 7: Прогнать наборы**

Run: `uv run pytest backend/core/tests/test_notifications.py backend/core/tests/test_payment_notifications.py backend/core/tests/test_email.py backend/core/tests/test_auto_renew.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/core/src/repibot_core/services/notifications.py \
        backend/core/src/repibot_core/services/payment_notifications.py \
        backend/core/src/repibot_core/services/dispatcher.py \
        backend/core/src/repibot_core/services/email_dispatch.py \
        backend/core/tests/test_notifications.py
git commit -m "feat: категория события решает, в какие каналы оно уйдёт"
```

---

### Task 3: Согласие на маркетинг

**Files:**
- Modify: `backend/core/src/repibot_core/db/models/user.py`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0015_marketing_opt_out.py`
- Modify: `backend/core/src/repibot_core/services/notifications.py`
- Modify: `backend/core/tests/test_notifications.py`

**Interfaces:**
- Produces `User.marketing_opt_out_at: datetime | None`.
- Consumes `NotificationService._channels` из задачи 2.

- [ ] **Step 1: Падающий тест**

```python
async def test_opted_out_user_gets_service_but_not_marketing(db_session: AsyncSession) -> None:
    """Отказ от новостей не должен отключать сообщение о потере доступа."""
    user = await _user(db_session, telegram=True, verified_email=False)
    user.marketing_opt_out_at = datetime.now(UTC)
    await db_session.flush()
    service = NotificationService(db_session)

    marketing = await service.enqueue(
        user_id=user.id, kind="winback_1", dedup_key="winback:9:step1:x", params={}
    )
    service_event = await service.enqueue(
        user_id=user.id, kind="expired", dedup_key="sub:9:expired:x", params={}
    )
    await db_session.commit()

    assert (marketing, service_event) == (0, 1)
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_notifications.py -k opted_out -q`
Expected: FAIL — у `User` нет атрибута `marketing_opt_out_at`.

- [ ] **Step 3: Поле и миграция**

В `user.py` добавить в класс `User`:

```python
    # Хранится момент, а не флаг: при разборе жалобы важно, когда человек
    # отказался, — до рассылки или после неё.
    marketing_opt_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`0015_marketing_opt_out.py`:

```python
"""Отказ от маркетинговых сообщений.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("marketing_opt_out_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "marketing_opt_out_at")
```

- [ ] **Step 4: Учесть отказ при выборе каналов**

В `notifications.py` заменить конец `_channels`:

```python
        if kind.category is NotificationCategory.service:
            return available
        if user.marketing_opt_out_at is not None:
            return []
        return available[:1]
```

- [ ] **Step 5: Прогнать набор**

Run: `uv run pytest backend/core/tests/test_notifications.py backend/core/tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/src/repibot_core/db/models/user.py \
        backend/core/src/repibot_core/db/migrations/versions/0015_marketing_opt_out.py \
        backend/core/src/repibot_core/services/notifications.py \
        backend/core/tests/test_notifications.py
git commit -m "feat: отказ от маркетинга не трогает сервисные уведомления"
```

---

### Task 4: Отписка одной кнопкой

**Files:**
- Create: `backend/core/src/repibot_core/services/unsubscribe.py`
- Create: `backend/core/tests/test_unsubscribe.py`
- Modify: `backend/api/src/repibot_api/routers/me.py`
- Modify: `backend/api/src/repibot_api/schemas.py`
- Create: `backend/api/tests/test_unsubscribe_routes.py`

**Interfaces:**
- Produces `sign_unsubscribe_token(user_id: int) -> str`,
  `UnsubscribeService.apply(token: str) -> None` (бросает `ServiceError("ссылка недействительна", "invalid_token")`),
  маршрут `POST /api/unsubscribe` с телом `{"token": "..."}` и ответом 204.
- Consumes `User.marketing_opt_out_at` из задачи 3, `Settings.jwt_secret`.

- [ ] **Step 1: Падающий тест сервиса**

`backend/core/tests/test_unsubscribe.py`:

```python
"""Отписка без входа: ссылка в письме и кнопка в Telegram."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.services.errors import ServiceError
from repibot_core.services.unsubscribe import UnsubscribeService, sign_unsubscribe_token

pytestmark = pytest.mark.docker


async def test_token_switches_marketing_off(db_session: AsyncSession) -> None:
    user = User(email=None, telegram_id=100_601, referral_code="unsub001")
    db_session.add(user)
    await db_session.flush()

    await UnsubscribeService(db_session).apply(sign_unsubscribe_token(user.id))
    await db_session.commit()

    assert user.marketing_opt_out_at is not None


async def test_foreign_signature_is_rejected(db_session: AsyncSession) -> None:
    """Токен подписан нашим секретом: подделка не должна отписывать чужого."""
    with pytest.raises(ServiceError) as failure:
        await UnsubscribeService(db_session).apply("не.наш.токен")

    assert failure.value.code == "invalid_token"
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_unsubscribe.py -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.services.unsubscribe`.

- [ ] **Step 3: Реализация**

`backend/core/src/repibot_core/services/unsubscribe.py`:

```python
"""Отказ от маркетинга по подписанной ссылке, без входа в аккаунт.

Требовать входа ради отписки значит удерживать человека там, откуда он хочет
уйти: он просто пометит письмо спамом, и это ударит по доставляемости всей
почты. Токен при этом не открывает ничего, кроме самой отписки.
"""

from __future__ import annotations

from datetime import UTC, datetime

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User
from repibot_core.services.errors import ServiceError
from repibot_core.settings import get_settings

PURPOSE = "unsubscribe"


def sign_unsubscribe_token(user_id: int) -> str:
    """Срока жизни нет намеренно: ссылка из письма годовой давности обязана работать."""
    return jwt.encode(
        {"sub": str(user_id), "purpose": PURPOSE},
        get_settings().jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


class UnsubscribeService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply(self, token: str) -> None:
        try:
            claims = jwt.decode(
                token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"]
            )
        except jwt.PyJWTError as error:
            raise ServiceError("ссылка недействительна", "invalid_token") from error
        # Назначение проверяется отдельно: access-токен подписан тем же
        # секретом, и без этой проверки он сошёл бы за ссылку отписки.
        if claims.get("purpose") != PURPOSE:
            raise ServiceError("ссылка недействительна", "invalid_token")

        user = await self._session.get(User, int(claims["sub"]))
        if user is None:
            raise ServiceError("ссылка недействительна", "invalid_token")
        if user.marketing_opt_out_at is None:
            user.marketing_opt_out_at = datetime.now(UTC)
```

- [ ] **Step 4: Падающий тест маршрута**

`backend/api/tests/test_unsubscribe_routes.py`:

```python
"""Отписка доступна без заголовка авторизации."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker


async def test_unsubscribe_needs_no_authorization(
    api_client: AsyncClient, user_headers: dict[str, str]
) -> None:
    me = await api_client.get("/api/me", headers=user_headers)
    from repibot_core.services.unsubscribe import sign_unsubscribe_token

    token = sign_unsubscribe_token(me.json()["id"])

    response = await api_client.post("/api/unsubscribe", json={"token": token})

    assert response.status_code == 204


async def test_bad_token_is_a_stable_error(api_client: AsyncClient) -> None:
    response = await api_client.post("/api/unsubscribe", json={"token": "чужой"})

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_token"
```

- [ ] **Step 5: Запустить и увидеть падение**

Run: `uv run pytest backend/api/tests/test_unsubscribe_routes.py -q`
Expected: FAIL — 404, маршрута нет.

- [ ] **Step 6: Маршрут**

В `schemas.py` добавить:

```python
class UnsubscribeRequest(BaseModel):
    token: str
```

В `me.py` — отдельный роутер без префикса `/api/me`, потому что этот маршрут
единственный в файле не требует авторизации:

```python
unsubscribe_router = APIRouter(prefix="/api", tags=["me"])


@unsubscribe_router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    payload: UnsubscribeRequest, session: Annotated[AsyncSession, Depends(db_session)]
) -> None:
    """Без авторизации: человек с почты не входит в аккаунт, чтобы отписаться."""
    try:
        await UnsubscribeService(session).apply(payload.token)
    except ServiceError as error:
        raise api_error_from(error) from error
    await session.commit()
```

Зарегистрировать `unsubscribe_router` в `backend/api/src/repibot_api/main.py`
рядом с остальными роутерами. Проверить в `errors.py`, что код
`invalid_token` отображается в 400; если его там нет — добавить в словарь
соответствия.

- [ ] **Step 7: Кнопка в Telegram**

В `dispatcher.py`, в `handle_notify_telegram`, добавить кнопку для
маркетинговых видов:

```python
        markup = None
        if kind.category is NotificationCategory.marketing:
            # Отписка обязана быть на расстоянии одного касания: иначе человек
            # блокирует бота, и мы теряем и сервисные сообщения тоже.
            markup = {
                "inline_keyboard": [
                    [{"text": translate(language, "notify.unsubscribe"), "callback_data": "unsub"}]
                ]
            }
        await telegram.send_message(recipient, text, reply_markup=markup)
```

В `bot_api.py` расширить `send_message` необязательным
`reply_markup: dict[str, object] | None = None` и класть его в тело запроса,
только когда он не `None`.

В `backend/bot/src/repibot_bot/handlers/` создать `notifications.py` с
роутером, обрабатывающим `callback_data == "unsub"`: он вызывает
`UnsubscribeService.apply(sign_unsubscribe_token(user.id))` и отвечает
`translate(language, "notify.unsubscribed")`. Зарегистрировать роутер в
`build_dispatcher` в `backend/bot/src/repibot_bot/main.py`.

- [ ] **Step 8: Ссылка в письме**

В `email_dispatch.py` дописывать к телу маркетинговых писем строку
`translate(language, "notify.unsubscribe_link", link=...)`, где ссылка —
`f"{get_settings().public_web_url}/unsubscribe?token={sign_unsubscribe_token(user_id)}"`.
Идентификатор берётся из полезной нагрузки очереди ключом `user_id` — он там
уже есть с задачи 2.

Создать страницу `frontend/apps/web/src/app/unsubscribe/page.tsx`: читает
`token` из строки запроса, отправляет `POST /api/unsubscribe` и показывает
результат. Страница публичная, гейта на ней нет.

- [ ] **Step 9: Прогнать наборы**

Run: `uv run pytest backend/core/tests/test_unsubscribe.py backend/api/tests/test_unsubscribe_routes.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/core/src/repibot_core/services/unsubscribe.py \
        backend/core/src/repibot_core/services/dispatcher.py \
        backend/core/src/repibot_core/services/email_dispatch.py \
        backend/core/src/repibot_core/services/notifications.py \
        backend/core/src/repibot_core/integrations/telegram/bot_api.py \
        backend/bot/src/repibot_bot/handlers/notifications.py \
        backend/bot/src/repibot_bot/main.py \
        backend/api/src/repibot_api/routers/me.py \
        backend/api/src/repibot_api/schemas.py \
        backend/api/src/repibot_api/main.py \
        frontend/apps/web/src/app/unsubscribe/page.tsx \
        backend/core/tests/test_unsubscribe.py \
        backend/api/tests/test_unsubscribe_routes.py
git commit -m "feat: отписка одной кнопкой из письма и из Telegram"
```

---

### Task 5: Очередь перестаёт быть узким местом

**Files:**
- Modify: `backend/core/src/repibot_core/services/outbox.py:43-94`
- Modify: `backend/core/src/repibot_core/tasks.py:41-62`
- Modify: `backend/core/src/repibot_core/settings.py`
- Modify: `backend/core/tests/test_outbox_service.py`

**Interfaces:**
- Produces `OutboxDispatcher.process(session, *, limit=None, concurrency=None, now=None) -> int`,
  `OutboxDispatcher.drain(factory, *, max_seconds=50.0) -> int`.
- Consumes `OutboxRepository.take_batch`, `Settings.outbox_batch_size`,
  `Settings.outbox_concurrency`.

- [ ] **Step 1: Падающий тест параллельности**

Добавить в `backend/core/tests/test_outbox_service.py`:

```python
async def test_batch_is_sent_in_parallel_within_the_limit(db_session: AsyncSession) -> None:
    """Последовательная отправка даёт потолок в 1200 сообщений в час.

    Столько же занимает одна рассылка средней базы. Отправки идут
    одновременно, но не больше заданного числа: провайдер не должен получить
    сотню запросов разом.
    """
    repository = OutboxRepository(db_session)
    for index in range(20):
        await repository.add("notify.telegram", {"n": index})
    await db_session.commit()

    running = 0
    peak = 0

    async def slow(_: dict[str, object]) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0)
        running -= 1

    dispatcher = OutboxDispatcher()
    dispatcher.register("notify.telegram", slow)

    delivered = await dispatcher.process(db_session, limit=20, concurrency=10)

    assert delivered == 20
    assert peak == 10
```

Импорт: `import asyncio`.

- [ ] **Step 2: Падающий тест дренажа**

```python
async def test_drain_empties_a_queue_longer_than_one_batch(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Крон идёт раз в минуту: остаток пачки не должен ждать следующей минуты."""
    from repibot_core.db.engine import create_session_factory

    repository = OutboxRepository(db_session)
    for index in range(150):
        await repository.add("notify.telegram", {"n": index})
    await db_session.commit()

    async def noop(_: dict[str, object]) -> None:
        return None

    dispatcher = OutboxDispatcher()
    dispatcher.register("notify.telegram", noop)

    delivered = await dispatcher.drain(create_session_factory(engine))

    assert delivered == 150
```

- [ ] **Step 3: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_outbox_service.py -k "in_parallel or drain" -q`
Expected: FAIL — `process()` не принимает `concurrency`, `drain` не существует.

- [ ] **Step 4: Реализация**

В `outbox.py` заменить `process` и добавить `drain`:

```python
    async def process(
        self,
        session: AsyncSession,
        *,
        limit: int | None = None,
        concurrency: int | None = None,
        now: datetime | None = None,
    ) -> int:
        """Обрабатывает пачку сообщений. Возвращает число доставленных.

        Отправки идут одновременно, а записи в базу — по очереди: одна сессия
        SQLAlchemy не переживает параллельных запросов, и попытка сэкономить
        здесь даёт `InterfaceError` вместо ускорения.
        """
        settings = get_settings()
        size = limit if limit is not None else settings.outbox_batch_size
        parallel = concurrency if concurrency is not None else settings.outbox_concurrency
        moment = now or datetime.now(UTC)
        repository = OutboxRepository(session)

        pending: list[OutboxMessage] = []
        for message in await repository.take_batch(limit=size, now=moment):
            handler = self._handlers.get(message.topic)
            if handler is None:
                # Тема появится после выката новой версии. Сообщение остаётся
                # в очереди: терять его из-за порядка обновления сервисов нельзя.
                await repository.postpone(
                    message, f"нет обработчика для темы {message.topic}", RETRY_DELAYS[0]
                )
                continue
            pending.append(message)

        semaphore = asyncio.Semaphore(parallel)

        async def run(message: OutboxMessage) -> Exception | None:
            async with semaphore:
                try:
                    await self._handlers[message.topic](message.payload)
                # Ловим всё: падение одного обработчика не должно останавливать
                # разбор остальных сообщений.
                except Exception as error:
                    return error
                return None

        outcomes = await asyncio.gather(*(run(message) for message in pending))

        delivered = 0
        for message, error in zip(pending, outcomes, strict=True):
            if error is None:
                await _mark_delivery(session, message.payload, status="sent", error=None)
                await repository.mark_processed(message)
                delivered += 1
                continue
            attempt = message.attempts
            if attempt + 1 >= MAX_ATTEMPTS:
                # Попытки исчерпаны. Сообщение закрывается с сохранённой
                # ошибкой: висящая вечно строка мешает разбирать остальные.
                message.last_error = str(error)[:1000]
                message.attempts = attempt + 1
                await _mark_delivery(
                    session, message.payload, status="failed", error=message.last_error
                )
                await repository.mark_processed(message)
                logger.error(
                    "сообщение outbox отброшено после %s попыток",
                    MAX_ATTEMPTS,
                    extra={"topic": message.topic, "outbox_id": message.id},
                )
            else:
                await repository.postpone(message, str(error), RETRY_DELAYS[attempt])
                logger.warning(
                    "сообщение outbox отложено",
                    extra={"topic": message.topic, "outbox_id": message.id},
                )

        await session.commit()
        return delivered

    async def drain(
        self, factory: async_sessionmaker[AsyncSession], *, max_seconds: float = 50.0
    ) -> int:
        """Разбирает очередь до пустоты или до истечения времени прогона.

        Потолок по времени, а не по числу пачек: задача идёт раз в минуту, и
        прогон, переживший следующий запуск, разбирал бы очередь вдвоём сам с
        собой. Своя сессия на пачку: `process` закрывает транзакцию commit'ом.
        """
        size = get_settings().outbox_batch_size
        deadline = time.monotonic() + max_seconds
        delivered = 0
        while time.monotonic() < deadline:
            async with factory() as session:
                batch = await self.process(session)
            delivered += batch
            if batch < size:
                break
        return delivered
```

Импорты в начало файла: `import asyncio`, `import time`,
`from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker`,
`from repibot_core.db.models import OutboxMessage`,
`from repibot_core.settings import get_settings`.

Замечание к `drain`: выход по `batch < size` считает доставленные, а не
взятые. Пачка, целиком состоящая из отложенных сообщений, вернёт ноль и
прервёт цикл — это верно, потому что отложенные всё равно недоступны до
истечения задержки.

- [ ] **Step 5: Настройки**

В `settings.py` добавить в класс `Settings`:

```python
    # Пачка и параллельность разбора очереди. Сто и десять дают около десяти
    # тысяч сообщений в час — этого хватает базе в десятки тысяч человек в
    # день, когда у многих совпадает дата окончания.
    outbox_batch_size: int = Field(default=100, ge=1, le=1000)
    outbox_concurrency: int = Field(default=10, ge=1, le=50)
```

- [ ] **Step 6: Задача пользуется дренажом**

В `tasks.py` заменить тело `process_outbox`:

```python
        factory = create_session_factory(engine)
        delivered = await _dispatcher(factory, panel, telegram).drain(factory)
```

- [ ] **Step 7: Прогнать наборы**

Run: `uv run pytest backend/core/tests/test_outbox_service.py backend/core/tests/test_notifications.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/core/src/repibot_core/services/outbox.py \
        backend/core/src/repibot_core/tasks.py \
        backend/core/src/repibot_core/settings.py \
        backend/core/tests/test_outbox_service.py
git commit -m "perf: разбирать очередь пачками и параллельно"
```

---

### Task 6: Переключатель в кабинете и Mini App

**Files:**
- Modify: `backend/api/src/repibot_api/routers/me.py`
- Modify: `backend/api/src/repibot_api/schemas.py`
- Modify: `backend/api/tests/test_me_routes.py`
- Create: `frontend/packages/core/src/notifications/hooks.tsx`
- Create: `frontend/packages/core/src/notifications/hooks.test.tsx`
- Modify: `frontend/packages/core/src/index.ts`
- Modify: `frontend/packages/core/src/i18n/ru.ts`, `frontend/packages/core/src/i18n/en.ts`
- Create: `frontend/apps/web/src/app/account/notifications/page.tsx`
- Create: `frontend/apps/web/src/app/account/notifications/page.test.tsx`
- Modify: `frontend/apps/web/src/components/account-shell.tsx:13-18`
- Modify: `frontend/apps/miniapp/src/routes/profile.tsx`
- Modify: `frontend/apps/miniapp/src/routes/profile.test.tsx`

**Interfaces:**
- Produces `GET /api/me/notifications` → `{"marketing_enabled": bool}`,
  `PATCH /api/me/notifications` с телом `{"marketing_enabled": bool}` → то же тело;
  хуки `useNotificationSettings()` и `useUpdateNotificationSettings()`.
- Consumes `User.marketing_opt_out_at` из задачи 3.

- [ ] **Step 1: Падающий тест API**

Добавить в `backend/api/tests/test_me_routes.py`:

```python
async def test_marketing_toggle_round_trips(
    api_client: AsyncClient, user_headers: dict[str, str]
) -> None:
    """Случайная отписка обязана отменяться там же, где сделана."""
    default = await api_client.get("/api/me/notifications", headers=user_headers)
    off = await api_client.patch(
        "/api/me/notifications", headers=user_headers, json={"marketing_enabled": False}
    )
    on = await api_client.patch(
        "/api/me/notifications", headers=user_headers, json={"marketing_enabled": True}
    )

    assert default.json() == {"marketing_enabled": True}
    assert off.json() == {"marketing_enabled": False}
    assert on.json() == {"marketing_enabled": True}
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/api/tests/test_me_routes.py -k marketing_toggle -q`
Expected: FAIL — 404.

- [ ] **Step 3: Маршруты**

В `schemas.py`:

```python
class NotificationSettingsResponse(BaseModel):
    marketing_enabled: bool


class UpdateNotificationSettingsRequest(BaseModel):
    marketing_enabled: bool
```

В `me.py`:

```python
@router.get("/notifications", response_model=NotificationSettingsResponse)
async def notification_settings(
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> NotificationSettingsResponse:
    user = await session.get(User, context.principal.user_id)
    assert user is not None
    return NotificationSettingsResponse(marketing_enabled=user.marketing_opt_out_at is None)


@router.patch("/notifications", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    payload: UpdateNotificationSettingsRequest,
    context: Annotated[AuthContext, Depends(current_context)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> NotificationSettingsResponse:
    user = await session.get(User, context.principal.user_id)
    assert user is not None
    # Повторное включение не двигает момент отказа в прошлом: колонка либо
    # пуста, либо хранит время последнего отказа.
    user.marketing_opt_out_at = None if payload.marketing_enabled else datetime.now(UTC)
    await session.commit()
    return NotificationSettingsResponse(marketing_enabled=payload.marketing_enabled)
```

Импорты: `from datetime import UTC, datetime`, `from repibot_core.db.models import User`.

- [ ] **Step 4: Пересобрать типы клиента**

Run: `uv run generate-openapi && cd frontend && pnpm generate`
(точные имена команд смотреть в `pyproject.toml` и `frontend/package.json`;
проверка `uv run verify-generated` обязана стать зелёной).

- [ ] **Step 5: Падающий тест хука**

`frontend/packages/core/src/notifications/hooks.test.tsx`:

```tsx
import { describe, expect, it } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

import { useNotificationSettings } from './hooks'
import { withQueryClient } from '../test-utils'

describe('useNotificationSettings', () => {
  it('читает текущее согласие', async () => {
    const { result } = renderHook(() => useNotificationSettings(), { wrapper: withQueryClient() })

    await waitFor(() => expect(result.current.data).toEqual({ marketing_enabled: true }))
  })
})
```

Обёртку и подмену `fetch` брать той же, что уже используют
`frontend/packages/core/src/subscription/hooks.test.tsx`; повторить её схему,
а не изобретать вторую.

- [ ] **Step 6: Реализация хуков**

`frontend/packages/core/src/notifications/hooks.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'

const KEY = ['notification-settings'] as const

export function useNotificationSettings() {
  return useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const { data } = await api.GET('/api/me/notifications')
      return data
    },
  })
}

export function useUpdateNotificationSettings() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (marketingEnabled: boolean) => {
      const { data } = await api.PATCH('/api/me/notifications', {
        body: { marketing_enabled: marketingEnabled },
      })
      return data
    },
    // Ответ кладётся в кэш напрямую: сервер вернул то самое состояние,
    // и второй запрос за ним ничего не уточнит.
    onSuccess: (data) => client.setQueryData(KEY, data),
  })
}
```

Точную форму вызова `api.GET`/`api.PATCH` сверить с
`frontend/packages/core/src/payments/hooks.tsx`. Экспортировать оба хука из
`frontend/packages/core/src/index.ts`.

- [ ] **Step 7: Переводы**

В `ru.ts` и `en.ts` добавить ключи `notifications.title`,
`notifications.marketing`, `notifications.marketing_hint`,
`notifications.service_hint`. Русский текст подсказки:
«Сообщения об оплате, окончании подписки и ответах поддержки приходят всегда».

- [ ] **Step 8: Экран кабинета**

`frontend/apps/web/src/app/account/notifications/page.tsx` — клиентский
компонент с переключателем, вызывающим `useUpdateNotificationSettings`.
Добавить ссылку в `LINKS` в `account-shell.tsx`:

```tsx
  { href: '/account/notifications', key: 'notifications.title' },
```

- [ ] **Step 9: Переключатель в Mini App**

В `frontend/apps/miniapp/src/routes/profile.tsx` добавить секцию после блока
языка, повторяющую разметку соседних секций и использующую те же хуки.

- [ ] **Step 10: Тесты экранов**

`page.test.tsx` для веба и дополнение `profile.test.tsx` для Mini App:
переключатель виден, нажатие отправляет `PATCH` с `marketing_enabled: false`,
подсказка про сервисные сообщения на экране есть.

- [ ] **Step 11: Прогнать**

Run: `cd frontend && pnpm test` и `uv run pytest backend/api/tests/test_me_routes.py -q`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add backend/api/src/repibot_api/routers/me.py \
        backend/api/src/repibot_api/schemas.py \
        backend/api/tests/test_me_routes.py \
        frontend/packages/core/src/notifications \
        frontend/packages/core/src/index.ts \
        frontend/packages/core/src/i18n \
        frontend/packages/core/src/api/schema.d.ts \
        frontend/apps/web/src/app/account/notifications \
        frontend/apps/web/src/components/account-shell.tsx \
        frontend/apps/miniapp/src/routes/profile.tsx \
        frontend/apps/miniapp/src/routes/profile.test.tsx
git commit -m "feat: переключатель маркетинговых сообщений в кабинете и Mini App"
```

---

### Task 7: Документация и полная проверка

**Files:**
- Modify: `docs/deployment.md`

- [ ] **Step 1: Описать новые настройки**

Добавить в раздел переменных окружения строки `OUTBOX_BATCH_SIZE` и
`OUTBOX_CONCURRENCY` с умолчаниями 100 и 10 и объяснением, что их поднимают,
когда очередь не успевает разбираться за минуту.

- [ ] **Step 2: Описать диагностику**

Добавить строку в таблицу диагностики: «Уведомления приходят с задержкой» →
`select count(*) from outbox where processed_at is null` в контейнере базы;
если число растёт от прогона к прогону, поднимать `OUTBOX_BATCH_SIZE`.

- [ ] **Step 3: Полная проверка**

Run: `uv run check`
Expected: все восемь проверок зелёные.

- [ ] **Step 4: Commit**

```bash
git add docs/deployment.md
git commit -m "docs: настройки пропускной способности очереди"
```

---

## Plan Self-Review

**Покрытие спецификации.** Раздел 3 «Обобщение доставок» — задача 1. Раздел 3
«Согласие» — задача 3. Раздел 4 «Категории, каналы и согласие» — задачи 2 и 4.
Раздел 5 «Пропускная способность» — задача 5. Раздел 11 «Пользователь»
в части настроек и отписки — задачи 4 и 6. Разделы 6–9 закрывают планы
2–5 этого подпроекта.

**Заглушки.** Не найдено. Два места намеренно отправляют исполнителя смотреть
соседний файл вместо копии кода: форма вызова `api.GET` в задаче 6 и обёртка
теста хука — оба раза потому, что копия устареет раньше оригинала.

**Согласованность имён.** `dedup_key` (задача 1) → `NotificationService.enqueue`
(задача 2) → `_channels` с учётом отказа (задача 3). `sign_unsubscribe_token`
и `UnsubscribeService.apply` (задача 4) используются и ботом, и почтой, и
маршрутом. `outbox_batch_size`/`outbox_concurrency` (задача 5) читаются в
`process` и `drain`. `marketing_enabled` — единственное имя поля в API и
хуках (задача 6), в базе ему соответствует `marketing_opt_out_at`.
