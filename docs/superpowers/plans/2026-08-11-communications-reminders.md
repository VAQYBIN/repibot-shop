# Поводы уведомлений Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Человек узнаёт, что подписка кончается, что она кончилась и что счёт
остался неоплаченным, — по одному разу на повод, независимо от того, сколько
раз перезапускался крон.

**Architecture:** Один крон `notify_subscription_events` раз в час собирает все
четыре повода и ставит их через `NotificationService.enqueue` из плана
«Слой доставки». Дедупликацию обеспечивает ключ: в него входит дата окончания
подписки, поэтому продление честно открывает новый цикл напоминаний, а
повторный запуск в том же цикле — нет. Напоминание об истечении не ставится
подписке с работающим автопродлением: у неё уже есть своё уведомление о
неудаче.

**Tech Stack:** Python 3.13, SQLAlchemy 2 async/PostgreSQL 18, TaskIQ/Valkey,
pytest.

## Global Constraints

- Этот план начинается после плана «Слой доставки и согласие»: он опирается на
  `NotificationService.enqueue(*, user_id, kind, dedup_key, params, order_id=None)`,
  реестр видов `resolve_kind` и категорию `service`.
- Формы ключей заданы спецификацией и не сокращаются:
  `sub:{subscription_id}:expiring:{days}:{expires_at}`,
  `sub:{subscription_id}:expired:{expires_at}`, `order:{order_id}:unpaid`.
  Дата окончания записывается через `expires_at.astimezone(UTC).isoformat()`.
- Все четыре повода — категория `service`: их нельзя отключить.
- Пороги задаются настройками `EXPIRY_REMINDER_DAYS` (умолчание `3,1`) и
  `UNPAID_INVOICE_AFTER_MINUTES` (умолчание `30`).
- Порог из настройки превращается в вид уведомления `expiring_{days}`, а вид
  обязан быть в реестре `_KINDS` и иметь тексты. Поэтому допустимы только
  пороги 3 и 1; добавление третьего — это задача, а не правка `.env`. Это
  ограничение проверяется тестом в задаче 1 и повторено в документации.
- Все комментарии и докстринги на русском и объясняют «почему».
- Каждая задача: сначала падающий тест, обязательно запущенный и увиденный
  красным, затем минимальная реализация, затем тематический commit на ветке
  `dev`. Полный `uv run check` — перед сдачей плана.
- Строки не длиннее 100 символов (ruff), переводы строк LF.

---

### Task 1: Настройки порогов и тексты

**Files:**
- Modify: `backend/core/src/repibot_core/settings.py`
- Modify: `backend/core/src/repibot_core/i18n.py`
- Create: `backend/core/tests/test_subscription_notices.py`

**Interfaces:**
- Produces `Settings.expiry_reminder_days: tuple[int, ...]`,
  `Settings.unpaid_invoice_after_minutes: int`; ключи i18n
  `subscription.expiring_3.*`, `subscription.expiring_1.*`,
  `subscription.expired.*`, `payment.unpaid.*` в вариантах `.bot`, `.subject`,
  `.body` на `ru` и `en`.
- Consumes реестр видов из плана «Слой доставки»: имена видов должны совпасть
  с `text_key` в `_KINDS`.

- [ ] **Step 1: Падающий тест разбора настройки**

`backend/core/tests/test_subscription_notices.py`:

```python
"""Напоминания о судьбе подписки."""

from __future__ import annotations

import pytest

from repibot_core.settings import Settings


def test_reminder_days_are_read_from_a_comma_separated_string() -> None:
    """В .env человек пишет список через запятую, а не JSON-массив."""
    settings = Settings(EXPIRY_REMINDER_DAYS="3, 1")  # type: ignore[call-arg]

    assert settings.expiry_reminder_days == (3, 1)


def test_every_threshold_has_a_registered_kind_and_texts() -> None:
    """Порог из .env превращается в вид уведомления, а вид нужно объявить.

    Без этой проверки строка EXPIRY_REMINDER_DAYS=7 роняла бы крон на живом
    стенде: resolve_kind не знает вида expiring_7, а translate — его текстов.
    """
    from repibot_core.i18n import translate
    from repibot_core.services.notifications import resolve_kind

    for days in Settings(EXPIRY_REMINDER_DAYS="3, 1").expiry_reminder_days:  # type: ignore[call-arg]
        kind = resolve_kind(f"expiring_{days}")
        assert translate("ru", f"{kind.text_key}.bot", plan="Месяц", date="01.01.2026")
```

Если конструктор `Settings` в наборе требует обязательных полей, собрать его
тем же способом, каким это делает `backend/core/tests/test_settings.py`, если
такой файл есть; иначе — через `monkeypatch.setenv` и `get_settings.cache_clear()`.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_subscription_notices.py -q`
Expected: FAIL — у `Settings` нет `expiry_reminder_days`.

- [ ] **Step 3: Настройки**

В `settings.py`, рядом с `admin_telegram_ids`, добавить:

```python
    # Список через запятую, как и у идентификаторов админов: NoDecode
    # отключает разбор значения как JSON, иначе строка "3, 1" падает раньше
    # валидатора.
    expiry_reminder_days: Annotated[tuple[int, ...], NoDecode] = (3, 1)
    unpaid_invoice_after_minutes: int = Field(default=30, ge=5, le=1440)
```

и валидатор рядом с `_split_admin_ids`:

```python
    @field_validator("expiry_reminder_days", mode="before")
    @classmethod
    def _split_reminder_days(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return tuple(int(part) for part in value.split(",") if part.strip())
```

- [ ] **Step 4: Тексты (уже на месте — только проверить)**

Ключи `subscription.expiring_3.*`, `subscription.expiring_1.*`,
`subscription.expired.*` и `payment.unpaid.*` уже добавлены в `i18n.py` вместе
с реестром видов: вид без текстов падает в `translate` у живого человека, и их
завели сразу под проверкой `test_every_declared_kind_has_texts_in_every_language`.

Ничего не добавляй. Открой `i18n.py`, убедись, что подстановки в текстах —
именно `{plan}` и `{date}` для трёх видов о подписке и `{plan}` с `{link}` для
неоплаченного счёта, и что твой сервис передаёт ровно эти параметры. Ниже —
тексты, которые там должны лежать. Русский:

```python
        "subscription.expiring_3.subject": "Подписка кончается через три дня",
        "subscription.expiring_3.body": (
            "Тариф «{plan}» действует до {date}. Продлите, чтобы доступ не прервался."
        ),
        "subscription.expiring_3.bot": (
            "Тариф «{plan}» действует до {date}. Продлите, чтобы доступ не прервался."
        ),
        "subscription.expiring_1.subject": "Подписка кончается завтра",
        "subscription.expiring_1.body": (
            "Тариф «{plan}» действует до {date}. Это последний день до перерыва в доступе."
        ),
        "subscription.expiring_1.bot": (
            "Тариф «{plan}» действует до {date}. Это последний день до перерыва в доступе."
        ),
        "subscription.expired.subject": "Подписка закончилась",
        "subscription.expired.body": (
            "Тариф «{plan}» закончился. Доступ отключён — продлите, чтобы вернуть его."
        ),
        "subscription.expired.bot": (
            "Тариф «{plan}» закончился. Доступ отключён — продлите, чтобы вернуть его."
        ),
        "payment.unpaid.subject": "Счёт ждёт оплаты",
        "payment.unpaid.body": (
            "Счёт на тариф «{plan}» ещё не оплачен. Открыть оплату:\n{link}"
        ),
        "payment.unpaid.bot": "Счёт на тариф «{plan}» ещё не оплачен. Открыть оплату:\n{link}",
```

Английский — те же ключи: `"Your {plan} plan is active until {date}. Renew to
keep access."`, `"Your {plan} plan is active until {date}. This is the last day
before access stops."`, `"Your {plan} plan has ended. Access is off — renew to
bring it back."`, `"The invoice for the {plan} plan is still unpaid. Open
payment:\n{link}"`, с соответствующими темами писем.

- [ ] **Step 5: Прогнать**

Run: `uv run pytest backend/core/tests/test_subscription_notices.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/src/repibot_core/settings.py \
        backend/core/src/repibot_core/i18n.py \
        backend/core/tests/test_subscription_notices.py
git commit -m "feat: пороги напоминаний и их тексты на двух языках"
```

---

### Task 2: Напоминания о судьбе подписки

**Files:**
- Create: `backend/core/src/repibot_core/services/subscription_notices.py`
- Modify: `backend/core/tests/test_subscription_notices.py`

**Interfaces:**
- Produces `SubscriptionNoticeService(session, settings=None)` с методом
  `run(*, now: datetime) -> int`, возвращающим число поставленных уведомлений.
- Consumes `NotificationService.enqueue`, `Subscription`, `Plan`,
  `PaymentMethodService.current_method_id(user_id) -> str | None`.

- [ ] **Step 1: Падающий тест трёх поводов**

Дописать в `backend/core/tests/test_subscription_notices.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    NotificationDelivery,
    Subscription,
    SubscriptionSource,
    TrafficResetStrategy,
    User,
)
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.subscription_notices import SubscriptionNoticeService

pytestmark = pytest.mark.docker


async def _subscriber(
    session: AsyncSession, *, expires_in: timedelta, status: SubscriptionState, telegram_id: int
) -> Subscription:
    user = User(email=None, telegram_id=telegram_id, referral_code=f"note{telegram_id}")
    session.add(user)
    plan = await PlanRepository(session).create(
        code=f"plan{telegram_id}",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=3,
        internal_squad_uuids=["11111111-1111-4111-8111-111111111111"],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    await session.flush()
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status=status,
        started_at=datetime.now(UTC) - timedelta(days=30),
        expires_at=datetime.now(UTC) + expires_in,
        auto_renew_enabled=False,
        source=SubscriptionSource.purchase,
        entitlement_price_rub=Decimal("299.00"),
        entitlement_duration_days=30,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def test_three_day_notice_is_staged_once_per_expiry_date(db_session: AsyncSession) -> None:
    """Перезапуск крона в том же цикле не должен слать второе напоминание."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=2, hours=12),
        status=SubscriptionState.active,
        telegram_id=101_001,
    )
    await db_session.commit()
    service = SubscriptionNoticeService(db_session)

    first = await service.run(now=datetime.now(UTC))
    second = await service.run(now=datetime.now(UTC))
    await db_session.commit()

    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert (first, second) == (1, 0)
    assert kinds == ["expiring_3"]
    assert subscription.id > 0


async def test_renewal_opens_a_new_cycle_of_notices(db_session: AsyncSession) -> None:
    """Новая дата окончания — новый повод напомнить, а не молчание навсегда."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=2, hours=12),
        status=SubscriptionState.active,
        telegram_id=101_002,
    )
    await db_session.commit()
    service = SubscriptionNoticeService(db_session)
    await service.run(now=datetime.now(UTC))

    subscription.expires_at = datetime.now(UTC) + timedelta(days=32, hours=12)
    await db_session.commit()
    after_renewal = await service.run(now=datetime.now(UTC) + timedelta(days=30))
    await db_session.commit()

    assert after_renewal == 1


async def test_expired_subscription_gets_its_own_notice(db_session: AsyncSession) -> None:
    await _subscriber(
        db_session,
        expires_in=timedelta(hours=-1),
        status=SubscriptionState.expired,
        telegram_id=101_003,
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert (staged, kinds) == (1, ["expired"])
```

- [ ] **Step 2: Падающий тест пропуска при автопродлении**

```python
async def test_working_auto_renewal_silences_the_expiry_notice(db_session: AsyncSession) -> None:
    """Незачем тревожить окончанием того, что продлится само.

    Если продление не сработает, придёт сообщение о неудаче — оно уже есть.
    """
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=2, hours=12),
        status=SubscriptionState.active,
        telegram_id=101_004,
    )
    subscription.auto_renew_enabled = True
    db_session.add(
        SavedPaymentMethod(
            user_id=subscription.user_id, provider_method_id="pm-1", title="Bank card *4444"
        )
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0
```

Точное имя и поля модели сохранённой карты взять из
`backend/core/src/repibot_core/db/models/commerce.py`; способ создания —
из `backend/core/tests/test_payment_methods.py`, чтобы не разойтись с тем,
как карта заводится в бою.

- [ ] **Step 3: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_subscription_notices.py -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.services.subscription_notices`.

- [ ] **Step 4: Реализация**

`backend/core/src/repibot_core/services/subscription_notices.py`:

```python
"""Напоминания о судьбе подписки.

Ключ дедупликации несёт дату окончания. Это единственное, что делает крон
безопасным при любом расписании: продление сдвигает дату и честно открывает
новый цикл, а повторный запуск в том же цикле не порождает второго письма.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Plan, Subscription
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.notifications import NotificationService
from repibot_core.services.payment_methods import PaymentMethodService
from repibot_core.settings import Settings, get_settings


class SubscriptionNoticeService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._notifications = NotificationService(session)

    async def run(self, *, now: datetime) -> int:
        staged = 0
        staged += await self._expiring(now)
        staged += await self._expired()
        return staged

    async def _expiring(self, now: datetime) -> int:
        staged = 0
        # Пороги по убыванию: подписка, которой остался день, подпадает и под
        # порог в три дня. Первым должен сработать более срочный, иначе
        # человек получит «через три дня» накануне отключения.
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

    async def _expired(self) -> int:
        rows = (
            await self._session.execute(
                select(Subscription, Plan.name)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.status == SubscriptionState.expired)
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

    async def _renews_itself(self, subscription: Subscription) -> bool:
        """Включённая настройка без карты — это не автопродление, а надежда."""
        if not subscription.auto_renew_enabled:
            return False
        method = await PaymentMethodService(self._session).current_method_id(subscription.user_id)
        return method is not None

    async def _stage(
        self, subscription: Subscription, plan_name: dict[str, str], *, kind: str, dedup_key: str
    ) -> int:
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
```

Замечание: название тарифа берётся по-русски, а язык письма — из профиля.
Это осознанное упрощение того же вида, что уже принято в
`NotificationService.enqueue_payment_event`, где имя берётся снимком заказа;
менять его в этом плане не нужно.

- [ ] **Step 5: Прогнать**

Run: `uv run pytest backend/core/tests/test_subscription_notices.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/src/repibot_core/services/subscription_notices.py \
        backend/core/tests/test_subscription_notices.py
git commit -m "feat: напоминать о конце подписки по одному разу на дату"
```

---

### Task 3: Неоплаченный счёт

**Files:**
- Modify: `backend/core/src/repibot_core/services/subscription_notices.py`
- Modify: `backend/core/tests/test_subscription_notices.py`

**Interfaces:**
- Produces метод `SubscriptionNoticeService._unpaid(now)`, включённый в `run`.
- Consumes `Order.status`, `Order.created_at`, `Order.expires_at`,
  `Settings.unpaid_invoice_after_minutes`, `Settings.public_app_url`.

- [ ] **Step 1: Падающий тест**

```python
async def test_unpaid_invoice_is_reminded_once(db_session: AsyncSession) -> None:
    """Одно напоминание на заказ: второе выглядит как требование долга."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=20),
        status=SubscriptionState.active,
        telegram_id=101_005,
    )
    plan = await db_session.get(Plan, subscription.plan_id)
    assert plan is not None
    order = await OrderRepository(db_session).create_pending(
        user_id=subscription.user_id,
        plan=plan,
        client_key="unpaid-1",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    order.created_at = datetime.now(UTC) - timedelta(minutes=40)
    await db_session.commit()
    service = SubscriptionNoticeService(db_session)

    first = await service.run(now=datetime.now(UTC))
    second = await service.run(now=datetime.now(UTC))
    await db_session.commit()

    staged = list(
        (
            await db_session.scalars(
                select(NotificationDelivery.kind).where(NotificationDelivery.order_id == order.id)
            )
        ).all()
    )
    assert (first - second, staged) == (1, ["unpaid_invoice"])
```

Импорт: `from repibot_core.db.repositories.orders import OrderRepository`.

- [ ] **Step 2: Падающий тест про свежий счёт**

```python
async def test_fresh_invoice_is_left_alone(db_session: AsyncSession) -> None:
    """Человек всё ещё на форме оплаты; торопить его нечем."""
    subscription = await _subscriber(
        db_session,
        expires_in=timedelta(days=20),
        status=SubscriptionState.active,
        telegram_id=101_006,
    )
    plan = await db_session.get(Plan, subscription.plan_id)
    assert plan is not None
    await OrderRepository(db_session).create_pending(
        user_id=subscription.user_id,
        plan=plan,
        client_key="fresh-1",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    await db_session.commit()

    staged = await SubscriptionNoticeService(db_session).run(now=datetime.now(UTC))
    await db_session.commit()

    assert staged == 0
```

- [ ] **Step 3: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_subscription_notices.py -k unpaid -q`
Expected: FAIL — напоминание не ставится.

- [ ] **Step 4: Реализация**

Добавить в `SubscriptionNoticeService`:

```python
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
                params={"plan": title, "link": f"{self._settings.public_app_url}/payments"},
                order_id=order.id,
            )
        return staged
```

и вызвать его в `run`: `staged += await self._unpaid(now)`.

Импорты: `from repibot_core.db.models import Order, OrderStatus, Plan, Subscription`.

- [ ] **Step 5: Прогнать**

Run: `uv run pytest backend/core/tests/test_subscription_notices.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/src/repibot_core/services/subscription_notices.py \
        backend/core/tests/test_subscription_notices.py
git commit -m "feat: одно напоминание о неоплаченном счёте"
```

---

### Task 4: Крон и документация

**Files:**
- Modify: `backend/core/src/repibot_core/tasks.py`
- Create: `backend/core/tests/test_notice_task.py`
- Modify: `docs/deployment.md`

**Interfaces:**
- Produces задачу `notify_subscription_events` с расписанием `"7 * * * *"`.
- Consumes `SubscriptionNoticeService.run`.

- [ ] **Step 1: Падающий тест задачи**

`backend/core/tests/test_notice_task.py`:

```python
"""Задача напоминаний живёт своим расписанием и закрывает движок."""

from __future__ import annotations

import pytest

from repibot_core.tasks import notify_subscription_events

pytestmark = pytest.mark.docker


def test_notices_run_hourly_off_the_hour() -> None:
    """Смещение от нуля минут: в ноль уже стоит истечение подписок.

    Два крона, стартующих одновременно, дерутся за одни и те же строки
    подписок, и напоминание уходит про состояние, которое вот-вот изменится.
    """
    schedule = notify_subscription_events.labels["schedule"]

    assert schedule == [{"cron": "7 * * * *"}]
```

Точное имя атрибута расписания подсмотреть в существующем тесте задач, если
он есть, либо в объявлении `@broker.task(schedule=...)`; если у TaskIQ нет
публичного доступа к расписанию, заменить проверку на утверждение, что вызов
`notify_subscription_events.original_func()` на пустой базе возвращает
`{"staged": 0}`.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_notice_task.py -q`
Expected: FAIL — `ImportError: cannot import name 'notify_subscription_events'`.

- [ ] **Step 3: Реализация**

В `tasks.py`:

```python
@broker.task(schedule=[{"cron": "7 * * * *"}])
async def notify_subscription_events() -> dict[str, int]:
    """Ставит напоминания о конце подписки и о неоплаченном счёте.

    Раз в час и со смещением от нуля минут: в ноль работает истечение
    подписок, и запуск встык дал бы напоминание про состояние, которое
    меняется прямо сейчас. Отправку делает разбор очереди — здесь только
    постановка, поэтому задача не ходит ни в Telegram, ни в SMTP.
    """
    from repibot_core.services.subscription_notices import SubscriptionNoticeService

    engine = create_engine(get_settings().database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            staged = await SubscriptionNoticeService(session).run(now=datetime.now(UTC))
            await session.commit()
    finally:
        await engine.dispose()
    return {"staged": staged}
```

- [ ] **Step 4: Разбудить очередь**

В конце задачи, перед `return`, поставить пробуждение разбора — тем же
способом, каким это делает вебхук в
`backend/api/src/repibot_api/routers/webhooks.py` (`process_outbox.kiq()` в
`try/except`). Без него напоминание ждёт до минуты, хотя уже готово.

- [ ] **Step 5: Документация**

В `docs/deployment.md` добавить строки `EXPIRY_REMINDER_DAYS` и
`UNPAID_INVOICE_AFTER_MINUTES` в таблицу переменных и строку в таблицу
расписаний: `notify_subscription_events` — каждый час на седьмой минуте.

- [ ] **Step 6: Полная проверка**

Run: `uv run check`
Expected: все восемь проверок зелёные.

- [ ] **Step 7: Commit**

```bash
git add backend/core/src/repibot_core/tasks.py \
        backend/core/tests/test_notice_task.py \
        docs/deployment.md
git commit -m "feat: почасовой крон напоминаний о подписке и счёте"
```

---

## Plan Self-Review

**Покрытие спецификации.** Раздел 6 «Поводы уведомлений» закрыт целиком:
четыре повода из таблицы — задачи 2 и 3, пропуск при работающем
автопродлении — задача 2, разовое напоминание о счёте — задача 3, крон —
задача 4. Настройки `EXPIRY_REMINDER_DAYS` и `UNPAID_INVOICE_AFTER_MINUTES`
из раздела 10 — задача 1.

**Заглушки.** Не найдено. Три места отправляют исполнителя за точным именем в
существующий код (модель сохранённой карты, способ сборки `Settings` в тестах,
атрибут расписания TaskIQ) — каждый раз потому, что копия здесь устареет
раньше оригинала, и каждый раз с указанием запасного варианта.

**Согласованность имён.** Виды `expiring_3`, `expiring_1`, `expired`,
`unpaid_invoice` совпадают с реестром `_KINDS` из плана «Слой доставки»;
их `text_key` — `subscription.expiring_3`, `subscription.expiring_1`,
`subscription.expired`, `payment.unpaid` — совпадают с ключами i18n задачи 1.
`SubscriptionNoticeService.run(*, now)` вызывается только из задачи 4.
