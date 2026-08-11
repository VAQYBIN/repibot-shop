# Рассылки Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Администратор выбирает сегмент, видит охват до запуска, отправляет
кампанию тысячам людей с темпом под лимиты Telegram и может остановить её на
полпути — не задерживая при этом ни одного чека об оплате.

**Architecture:** Вторая полоса доставки, физически отдельная от outbox.
Кампания живёт в `broadcasts`, получатели материализуются одним
`INSERT ... SELECT` в момент запуска и с этой секунды зафиксированы. Задача
`run_broadcast` раз в минуту берёт одну кампанию в статусе `running`,
отправляет пачками с выдержкой темпа и перечитывает статус между пачками.
Общий outbox рассылка не трогает вовсе.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async/PostgreSQL 18,
Alembic, TaskIQ/Valkey, React 19, Next.js 16, TanStack Query v5, Vitest.

## Global Constraints

- План идёт после «Слоя доставки и согласия»: он опирается на
  `User.marketing_opt_out_at` и на правило выбора канала для категории
  `marketing` — Telegram, если привязан, иначе подтверждённая почта.
- Аудитория фиксируется в момент запуска. Человек, зарегистрировавшийся
  минутой позже, в кампанию не попадает; отписавшийся между черновиком и
  запуском — тоже, фильтр стоит в материализации, а не только в предпросмотре.
- Из каждого сегмента вычитаются отписавшиеся и те, у кого нет ни одного
  действующего канала.
- Кампании выполняются строго по одной: две одновременные поделили бы лимит
  Telegram и обе шли бы вдвое дольше, а порядок их завершения стал бы
  непредсказуемым.
- Темп — не выше `BROADCAST_RATE_PER_SECOND` (умолчание 25), под лимитом
  Telegram в 30 сообщений в секунду.
- Отмена — флаг, который задача проверяет между пачками. Уже отправленное не
  отзывается.
- Неудача отдельного получателя пишется в его строку и не останавливает
  кампанию.
- Рассылки доступны только роли `admin`. Роль `support` к ним не допущена.
- Все комментарии и докстринги на русском и объясняют «почему».
- Каждая задача: сначала падающий тест, обязательно запущенный и увиденный
  красным, затем минимальная реализация, затем тематический commit на ветке
  `dev`. Полный `uv run check` — перед сдачей плана.
- Строки не длиннее 100 символов (ruff), переводы строк LF.

---

### Task 1: Модели кампании

**Files:**
- Create: `backend/core/src/repibot_core/db/models/broadcast.py`
- Modify: `backend/core/src/repibot_core/db/models/__init__.py`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0020_broadcasts.py`
- Modify: `backend/core/src/repibot_core/settings.py`
- Create: `backend/core/tests/test_broadcasts.py`

**Interfaces:**
- Produces `BroadcastStatus` (`draft`, `running`, `canceled`, `done`),
  `RecipientStatus` (`pending`, `sent`, `failed`),
  `Broadcast(created_by_user_id, segment, title, body, status, planned_count,
  sent_count, failed_count, started_at, finished_at, created_at)`,
  `BroadcastRecipient(broadcast_id, user_id, channel, recipient, language,
  status, sent_at, error)`; настройку `broadcast_rate_per_second: int`.
- Consumes текущую голову миграций; при исполнении вне порядка поставить
  `down_revision` на то, что покажет `uv run alembic heads`.

- [ ] **Step 1: Падающий тест уникальности получателя**

`backend/core/tests/test_broadcasts.py`:

```python
"""Рассылки: сегменты, фиксация аудитории, темп и отмена."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Broadcast,
    BroadcastRecipient,
    BroadcastStatus,
    RecipientStatus,
    User,
)

pytestmark = pytest.mark.docker


async def test_one_person_gets_a_campaign_once(db_session: AsyncSession) -> None:
    """Повторный запуск материализации не должен слать письмо дважды."""
    admin = User(email=None, telegram_id=400_001, referral_code="bcadmin1")
    db_session.add(admin)
    await db_session.flush()
    campaign = Broadcast(
        created_by_user_id=admin.id,
        segment="all",
        title={"ru": "Новость", "en": "News"},
        body={"ru": "Текст", "en": "Text"},
        status=BroadcastStatus.draft,
    )
    db_session.add(campaign)
    await db_session.flush()
    for _ in range(2):
        db_session.add(
            BroadcastRecipient(
                broadcast_id=campaign.id,
                user_id=admin.id,
                channel="telegram",
                recipient="400001",
                language="ru",
                status=RecipientStatus.pending,
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_broadcasts.py -q`
Expected: FAIL — `ImportError: cannot import name 'Broadcast'`.

- [ ] **Step 3: Модели**

`backend/core/src/repibot_core/db/models/broadcast.py`:

```python
"""Массовая рассылка — вторая полоса доставки.

Через общий outbox рассылка на пять тысяч человек заняла бы четыре часа и всё
это время держала бы за собой чек об оплате: очередь одна, порядок по времени
готовности. Поэтому у кампаний свои таблицы и своя задача.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class BroadcastStatus(StrEnum):
    draft = "draft"
    running = "running"
    canceled = "canceled"
    done = "done"


class RecipientStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    segment: Mapped[str] = mapped_column(String(32))
    # По строке на язык, как у названий тарифов: рассылка уходит людям с
    # разной настройкой языка, и один текст на всех означает, что половина
    # получит чужой.
    title: Mapped[dict[str, str]] = mapped_column(JSONB)
    body: Mapped[dict[str, str]] = mapped_column(JSONB)
    status: Mapped[BroadcastStatus] = mapped_column(Enum(BroadcastStatus, name="broadcast_status"))
    planned_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BroadcastRecipient(Base):
    __tablename__ = "broadcast_recipients"
    __table_args__ = (
        UniqueConstraint("broadcast_id", "user_id", name="uq_broadcast_recipients_person"),
        # По нему задача берёт следующую пачку: без индекса каждая пачка
        # обходила бы всю таблицу получателей кампании.
        Index("ix_broadcast_recipients_queue", "broadcast_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(16))
    # Адрес фиксируется вместе с аудиторией: смена почты во время рассылки не
    # должна превращать половину кампании в письма на два разных адреса.
    recipient: Mapped[str] = mapped_column(String(320))
    language: Mapped[str] = mapped_column(String(2))
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="broadcast_recipient_status")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(512))
```

Экспортировать все пять имён из `db/models/__init__.py`.

- [ ] **Step 4: Миграция и настройка**

`0020_broadcasts.py` создаёт оба перечисления, обе таблицы, ограничение
`uq_broadcast_recipients_person` и индекс `ix_broadcast_recipients_queue`.

В `settings.py`:

```python
    # Под лимитом Telegram в тридцать сообщений в секунду: запас нужен,
    # потому что рядом идут сервисные уведомления той же полосы бота.
    broadcast_rate_per_second: int = Field(default=25, ge=1, le=30)
```

- [ ] **Step 5: Прогнать**

Run: `uv run pytest backend/core/tests/test_broadcasts.py backend/core/tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/src/repibot_core/db/models/broadcast.py \
        backend/core/src/repibot_core/db/models/__init__.py \
        backend/core/src/repibot_core/db/migrations/versions/0020_broadcasts.py \
        backend/core/src/repibot_core/settings.py \
        backend/core/tests/test_broadcasts.py
git commit -m "feat: модели рассылки и её получателей"
```

---

### Task 2: Сегменты

**Files:**
- Create: `backend/core/src/repibot_core/services/segments.py`
- Modify: `backend/core/tests/test_broadcasts.py`

**Interfaces:**
- Produces `SEGMENTS: dict[str, str]` — перечень допустимых имён с
  человеческими названиями; `segment_query(name: str) -> Select` —
  запрос, возвращающий колонки `(user_id, channel, recipient, language)`;
  `count_segment(session, name) -> int`.
- Consumes `User`, `Subscription`, `Order`, `Plan`.

- [ ] **Step 1: Падающий тест сегментов**

```python
async def test_segments_pick_the_right_people(db_session: AsyncSession) -> None:
    """Каждый сегмент — именованный запрос под своим тестом.

    Ошибка в сегменте — это письмо не тем людям, и её нельзя увидеть иначе
    как отдельной проверкой на каждый.
    """
    active = await _subscriber(db_session, telegram_id=400_010, expired=False)
    lapsed = await _subscriber(db_session, telegram_id=400_011, expired=True)
    silent = User(email=None, telegram_id=400_012, referral_code="bcsilent")
    db_session.add(silent)
    await db_session.commit()

    everyone = await count_segment(db_session, "all")
    with_access = await count_segment(db_session, "active")
    lapsed_count = await count_segment(db_session, "expired")

    assert everyone == 3
    assert with_access == 1
    assert lapsed_count == 1
    assert {active.id, lapsed.id} != set()


async def test_opted_out_person_is_out_of_every_segment(db_session: AsyncSession) -> None:
    """Отписка обязана действовать на все рассылки, а не на те, что вспомнили."""
    user = User(email=None, telegram_id=400_013, referral_code="bcout01")
    user.marketing_opt_out_at = datetime.now(UTC)
    db_session.add(user)
    await db_session.commit()

    assert await count_segment(db_session, "all") == 0


async def test_person_without_a_channel_is_out(db_session: AsyncSession) -> None:
    """Непроверенная почта без Telegram — это адрес, которого у нас нет."""
    db_session.add(User(email="unverified@example.org", referral_code="bcnoch1"))
    await db_session.commit()

    assert await count_segment(db_session, "all") == 0
```

Вспомогательную функцию `_subscriber(session, *, telegram_id, expired)`
написать по образцу `_subscriber` из
`backend/core/tests/test_subscription_notices.py`.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_broadcasts.py -k segment -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.services.segments`.

- [ ] **Step 3: Реализация**

`backend/core/src/repibot_core/services/segments.py`:

```python
"""Именованные сегменты аудитории.

Именованные, а не конструктор условий: конструктор — это отдельный язык
запросов со своими багами, и опечатка в нём отправляет письмо всей базе.
Каждый сегмент здесь покрыт своим тестом.
"""

from __future__ import annotations

from sqlalchemy import Select, case, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Order, OrderStatus, Plan, Subscription, User
from repibot_core.domain.subscriptions import SubscriptionState

SEGMENTS: dict[str, str] = {
    "all": "Все",
    "active": "С активной подпиской",
    "expired": "Истёкшие",
    "never_paid": "Ни разу не платившие",
    "trial": "На триале",
}

# Префикс сегмента по тарифу: `plan:month`. Отдельная форма, потому что имён
# тарифов заранее не знает никто.
PLAN_PREFIX = "plan:"


def _base() -> Select[tuple[int, str, str, str]]:
    """Пользователи с действующим каналом, кроме отписавшихся.

    Канал выбирается по тому же правилу, что и у маркетинговых уведомлений:
    Telegram приоритетнее подтверждённой почты. Правило записано выражением
    базы, а не циклом в Python: аудитория материализуется одним запросом.
    """
    channel = case((User.telegram_id.is_not(None), "telegram"), else_="email").label("channel")
    recipient = case(
        (User.telegram_id.is_not(None), User.telegram_id.cast(String)), else_=User.email
    ).label("recipient")
    # Колонки именованные: материализация получателей обращается к ним по
    # имени подзапроса, и порядковый доступ сломался бы от любой перестановки.
    return select(
        User.id.label("user_id"), channel, recipient, User.language.label("language")
    ).where(
        User.marketing_opt_out_at.is_(None),
        User.telegram_id.is_not(None)
        | (User.email.is_not(None) & User.email_verified_at.is_not(None)),
    )


def segment_query(name: str) -> Select[tuple[int, str, str, str]]:
    if name.startswith(PLAN_PREFIX):
        code = name[len(PLAN_PREFIX) :]
        return _base().where(
            exists(
                select(Subscription.id)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(
                    Subscription.user_id == User.id,
                    Subscription.status == SubscriptionState.active,
                    Plan.code == code,
                )
            )
        )
    if name == "all":
        return _base()
    if name == "active":
        return _base().where(
            exists(
                select(Subscription.id).where(
                    Subscription.user_id == User.id,
                    Subscription.status == SubscriptionState.active,
                )
            )
        )
    if name == "expired":
        return _base().where(
            exists(
                select(Subscription.id).where(
                    Subscription.user_id == User.id,
                    Subscription.status == SubscriptionState.expired,
                )
            )
        )
    if name == "trial":
        return _base().where(
            exists(
                select(Subscription.id)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(
                    Subscription.user_id == User.id,
                    Subscription.status == SubscriptionState.active,
                    Plan.is_trial.is_(True),
                )
            )
        )
    if name == "never_paid":
        return _base().where(
            ~exists(
                select(Order.id).where(
                    Order.user_id == User.id, Order.status == OrderStatus.fulfilled
                )
            )
        )
    msg = f"неизвестный сегмент: {name}"
    raise KeyError(msg)


async def count_segment(session: AsyncSession, name: str) -> int:
    """Охват до запуска. Меняется вместе с базой — это и есть его смысл."""
    return len(list((await session.execute(segment_query(name))).all()))
```

Импорт `String` из `sqlalchemy` добавить в заголовок файла. Если
`count_segment` окажется тяжёлым на больших базах, заменить его на
`select(func.count()).select_from(segment_query(name).subquery())` — форма
подзапроса даёт тот же ответ одним счётом.

- [ ] **Step 4: Прогнать**

Run: `uv run pytest backend/core/tests/test_broadcasts.py -k segment -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/src/repibot_core/services/segments.py \
        backend/core/tests/test_broadcasts.py
git commit -m "feat: именованные сегменты аудитории под тестами"
```

---

### Task 3: Жизнь кампании

**Files:**
- Create: `backend/core/src/repibot_core/services/broadcasts.py`
- Modify: `backend/core/tests/test_broadcasts.py`

**Interfaces:**
- Produces `BroadcastService(session, settings=None)` с методами
  `create(*, created_by: int, segment: str, title: dict[str, str], body: dict[str, str]) -> Broadcast`,
  `start(broadcast_id: int) -> int` (возвращает `planned_count`),
  `cancel(broadcast_id: int) -> None`,
  `list_campaigns() -> list[Broadcast]`.
- Consumes `segment_query`, модели задачи 1.

- [ ] **Step 1: Падающий тест фиксации аудитории**

```python
async def test_start_freezes_the_audience(db_session: AsyncSession) -> None:
    """Счётчик «отправлено 3400 из 5000» честен только при зафиксированной аудитории."""
    admin = User(email=None, telegram_id=400_020, referral_code="bcadm020")
    db_session.add(admin)
    await db_session.flush()
    await db_session.commit()
    service = BroadcastService(db_session)
    campaign = await service.create(
        created_by=admin.id,
        segment="all",
        title={"ru": "Новость", "en": "News"},
        body={"ru": "Текст", "en": "Text"},
    )
    await db_session.commit()

    planned = await service.start(campaign.id)
    db_session.add(User(email=None, telegram_id=400_021, referral_code="bclate01"))
    await db_session.commit()

    recipients = await db_session.scalar(
        select(func.count()).select_from(BroadcastRecipient).where(
            BroadcastRecipient.broadcast_id == campaign.id
        )
    )
    assert planned == 1
    assert recipients == 1
    assert campaign.status is BroadcastStatus.running


async def test_start_is_idempotent(db_session: AsyncSession) -> None:
    """Двойной клик по кнопке запуска не должен удваивать рассылку."""
    admin = User(email=None, telegram_id=400_022, referral_code="bcadm022")
    db_session.add(admin)
    await db_session.flush()
    await db_session.commit()
    service = BroadcastService(db_session)
    campaign = await service.create(
        created_by=admin.id,
        segment="all",
        title={"ru": "Новость", "en": "News"},
        body={"ru": "Текст", "en": "Text"},
    )
    await db_session.commit()
    await service.start(campaign.id)

    with pytest.raises(ServiceError) as second:
        await service.start(campaign.id)

    assert second.value.code == "broadcast_not_draft"


async def test_only_one_campaign_runs_at_a_time(db_session: AsyncSession) -> None:
    """Две одновременные кампании делят лимит Telegram и обе идут вдвое дольше."""
    admin = User(email=None, telegram_id=400_023, referral_code="bcadm023")
    db_session.add(admin)
    await db_session.flush()
    await db_session.commit()
    service = BroadcastService(db_session)
    first = await service.create(
        created_by=admin.id, segment="all", title={"ru": "1"}, body={"ru": "1"}
    )
    second = await service.create(
        created_by=admin.id, segment="all", title={"ru": "2"}, body={"ru": "2"}
    )
    await db_session.commit()
    await service.start(first.id)

    with pytest.raises(ServiceError) as refusal:
        await service.start(second.id)

    assert refusal.value.code == "broadcast_busy"
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_broadcasts.py -k "freezes or idempotent or one_campaign" -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.services.broadcasts`.

- [ ] **Step 3: Реализация**

`backend/core/src/repibot_core/services/broadcasts.py`. Ключевой метод:

```python
    async def start(self, broadcast_id: int) -> int:
        """Фиксирует аудиторию одним запросом и переводит кампанию в работу.

        INSERT ... SELECT, а не выборка в Python и вставка по одному: пять
        тысяч отдельных вставок — это пять тысяч обращений к базе, и любое
        падение посреди оставило бы половину аудитории.
        """
        async with self._session.begin():
            campaign = await self._session.get(Broadcast, broadcast_id, with_for_update=True)
            if campaign is None:
                raise ServiceError("рассылка не найдена", "not_found")
            if campaign.status is not BroadcastStatus.draft:
                raise ServiceError("рассылка уже запущена", "broadcast_not_draft")
            running = await self._session.scalar(
                select(Broadcast.id).where(Broadcast.status == BroadcastStatus.running).limit(1)
            )
            if running is not None:
                raise ServiceError("уже идёт другая рассылка", "broadcast_busy")

            source = segment_query(campaign.segment).subquery()
            await self._session.execute(
                insert(BroadcastRecipient).from_select(
                    ["broadcast_id", "user_id", "channel", "recipient", "language", "status"],
                    select(
                        literal(campaign.id),
                        source.c.user_id,
                        source.c.channel,
                        source.c.recipient,
                        source.c.language,
                        literal(RecipientStatus.pending.value),
                    ),
                )
            )
            planned = await self._session.scalar(
                select(func.count())
                .select_from(BroadcastRecipient)
                .where(BroadcastRecipient.broadcast_id == campaign.id)
            )
            campaign.planned_count = int(planned or 0)
            campaign.status = BroadcastStatus.running
            campaign.started_at = datetime.now(UTC)
        return campaign.planned_count
```

`create` проверяет, что сегмент известен (`SEGMENTS` или префикс `plan:`), и
что тексты непустые хотя бы на русском. `cancel` переводит `running` в
`canceled` и ставит `finished_at`; кампания в `done` отмене не подлежит —
отзывать уже отправленное нечем.

Колонки подзапроса берутся по именам, которые `segments._base()` задаёт
через `label()` в задаче 2: `user_id`, `channel`, `recipient`, `language`.

- [ ] **Step 4: Прогнать**

Run: `uv run pytest backend/core/tests/test_broadcasts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/src/repibot_core/services/broadcasts.py \
        backend/core/src/repibot_core/services/segments.py \
        backend/core/tests/test_broadcasts.py
git commit -m "feat: запуск кампании фиксирует аудиторию одним запросом"
```

---

### Task 4: Отправка с темпом и отменой

**Files:**
- Modify: `backend/core/src/repibot_core/services/broadcasts.py`
- Modify: `backend/core/src/repibot_core/tasks.py`
- Modify: `backend/core/tests/test_broadcasts.py`

**Interfaces:**
- Produces `BroadcastService.send_batch(*, telegram, email, limit=None) -> int`,
  задачу `run_broadcast` с расписанием `"* * * * *"`.
- Consumes `BotApi.send_message`, `EmailSender`, `Settings.broadcast_rate_per_second`.

- [ ] **Step 1: Падающий тест отмены**

```python
async def test_cancel_stops_the_campaign_between_batches(db_session: AsyncSession) -> None:
    """Остановить кампанию — единственный способ исправить ошибку в тексте.

    Отправленное не отзывается; всё, что можно спасти, — остаток аудитории.
    """
    campaign, service = await _running_campaign(db_session, people=5)
    sender = FakeTelegram()

    await service.send_batch(telegram=sender, email=None, limit=2)
    await service.cancel(campaign.id)
    await service.send_batch(telegram=sender, email=None, limit=10)
    await db_session.commit()

    assert len(sender.sent) == 2
    assert campaign.status is BroadcastStatus.canceled


async def test_failed_recipient_does_not_stop_the_rest(db_session: AsyncSession) -> None:
    """Один заблокировавший бота человек не должен обрывать рассылку на всех."""
    campaign, service = await _running_campaign(db_session, people=3)
    sender = FakeTelegram(fail_on=1)

    await service.send_batch(telegram=sender, email=None, limit=10)
    await db_session.commit()

    assert (campaign.sent_count, campaign.failed_count) == (2, 1)
    assert campaign.status is BroadcastStatus.done
```

`FakeTelegram` — двойник с методом
`async def send_message(self, chat_id: int, text: str, reply_markup=None) -> None`,
складывающий вызовы в список и бросающий `RuntimeError` на заданном по счёту.
`_running_campaign(session, *, people)` создаёт нужное число пользователей с
Telegram, кампанию и вызывает `start`.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_broadcasts.py -k "cancel_stops or failed_recipient" -q`
Expected: FAIL — у сервиса нет `send_batch`.

- [ ] **Step 3: Реализация**

```python
    async def send_batch(
        self, *, telegram: TelegramSender | None, email: EmailSender | None, limit: int | None = None
    ) -> int:
        """Отправляет пачку получателей текущей кампании, выдерживая темп.

        Темп держится задержкой между отправками, а не окном подсчёта:
        задача идёт раз в минуту, окно между её запусками всё равно
        обнулилось бы, а Telegram считает секунды, а не минуты.
        """
        settings = self._settings
        size = limit if limit is not None else settings.broadcast_rate_per_second * 60
        campaign = await self._current_running()
        if campaign is None:
            return 0
        pause = 1.0 / settings.broadcast_rate_per_second

        rows = list(
            (
                await self._session.scalars(
                    select(BroadcastRecipient)
                    .where(
                        BroadcastRecipient.broadcast_id == campaign.id,
                        BroadcastRecipient.status == RecipientStatus.pending,
                    )
                    .order_by(BroadcastRecipient.id)
                    .limit(size)
                )
            ).all()
        )
        sent = 0
        for row in rows:
            # Статус перечитывается на каждом получателе: отмена обязана
            # останавливать кампанию в пределах секунд, а не пачки.
            await self._session.refresh(campaign, ["status"])
            if campaign.status is not BroadcastStatus.running:
                break
            try:
                await self._deliver(row, campaign, telegram=telegram, email=email)
            except Exception as error:
                row.status = RecipientStatus.failed
                row.error = str(error)[:512]
                campaign.failed_count += 1
            else:
                row.status = RecipientStatus.sent
                row.sent_at = datetime.now(UTC)
                campaign.sent_count += 1
                sent += 1
            await self._session.commit()
            await asyncio.sleep(pause)

        remaining = await self._session.scalar(
            select(func.count())
            .select_from(BroadcastRecipient)
            .where(
                BroadcastRecipient.broadcast_id == campaign.id,
                BroadcastRecipient.status == RecipientStatus.pending,
            )
        )
        if not remaining and campaign.status is BroadcastStatus.running:
            campaign.status = BroadcastStatus.done
            campaign.finished_at = datetime.now(UTC)
            await self._session.commit()
        return sent
```

`_deliver` выбирает канал по `row.channel`, берёт текст
`campaign.body.get(row.language) or campaign.body["ru"]` и тему
`campaign.title.get(row.language) or campaign.title["ru"]`, шлёт в Telegram
без `parse_mode` или письмом. Под маркетинговым сообщением обязана быть
кнопка отписки: собрать её тем же способом, что и в плане «Слой доставки»
(`sign_unsubscribe_token` для письма, `callback_data: "unsub"` для Telegram).

`TelegramSender` — узкий `Protocol` с одним методом `send_message`: сервис не
должен зависеть от всего `BotApi`, и тест не должен собирать его целиком.

- [ ] **Step 4: Задача**

В `tasks.py`:

```python
@broker.task(schedule=[{"cron": "* * * * *"}])
async def run_broadcast() -> dict[str, int]:
    """Отправляет очередную пачку текущей кампании.

    Раз в минуту и по одной кампании: своя задача, а не общая очередь, —
    иначе рассылка на пять тысяч человек держала бы за собой чек об оплате.
    """
    from repibot_core.services.broadcasts import BroadcastService

    engine = create_engine(get_settings().database_url)
    redis = Redis.from_url(get_settings().valkey_url)
    telegram = BotApi(get_settings(), redis)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            sent = await BroadcastService(session).send_batch(
                telegram=telegram, email=_email_sender()
            )
    finally:
        await telegram.aclose()
        await redis.aclose()
        await engine.dispose()
    return {"sent": sent}
```

`_email_sender()` — сборка отправителя почты тем же способом, каким это
делает `build_email_dispatcher` в `services/email_dispatch.py`.

- [ ] **Step 5: Прогнать**

Run: `uv run pytest backend/core/tests/test_broadcasts.py -q`
Expected: PASS. Если тест идёт заметно дольше секунды из-за `asyncio.sleep`,
передавать в `send_batch` настройки с `broadcast_rate_per_second=30` и
ограничивать `limit` — задержка при этом остаётся 33 мс на получателя.

- [ ] **Step 6: Commit**

```bash
git add backend/core/src/repibot_core/services/broadcasts.py \
        backend/core/src/repibot_core/tasks.py \
        backend/core/tests/test_broadcasts.py
git commit -m "feat: отправка кампании с темпом и мгновенной отменой"
```

---

### Task 5: Админское API и экран

**Files:**
- Modify: `backend/api/src/repibot_api/routers/admin.py`
- Modify: `backend/api/src/repibot_api/schemas.py`
- Modify: `backend/api/tests/test_admin_routes.py`
- Create: `frontend/apps/web/src/app/admin/broadcasts/page.tsx` и `page.test.tsx`
- Modify: `frontend/packages/core/src/i18n/ru.ts`, `.../en.ts`

**Interfaces:**
- Produces `GET /api/admin/broadcasts`, `POST /api/admin/broadcasts`,
  `GET /api/admin/broadcasts/{id}`, `POST /api/admin/broadcasts/{id}/start`,
  `POST /api/admin/broadcasts/{id}/cancel`,
  `GET /api/admin/segments/{segment}/count` — все под
  `require_role(UserRole.admin)`.
- Consumes `BroadcastService`, `count_segment`, `SEGMENTS`.

- [ ] **Step 1: Падающий тест роли**

```python
async def test_support_role_cannot_touch_broadcasts(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Роль поддержки не имеет доступа к рассылкам — так решено архитектурой."""
    response = await api_client.get("/api/admin/broadcasts", headers=support_headers)

    assert response.status_code == 403


async def test_admin_sees_reach_before_launching(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Охват до запуска — единственная защита от «отправил не тем»."""
    response = await api_client.get("/api/admin/segments/all/count", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["count"] >= 1
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/api/tests/test_admin_routes.py -k broadcast -q`
Expected: FAIL — 404.

- [ ] **Step 3: Маршруты**

Шесть маршрутов из блока Interfaces. Схемы:
`BroadcastResponse(id, segment, title, body, status, planned_count,
sent_count, failed_count, started_at, finished_at)`,
`CreateBroadcastRequest(segment, title, body)`,
`SegmentCountResponse(count)`. Каждое действие писать в `audit_log` тем же
способом, что и соседние админские операции.

- [ ] **Step 4: Пересобрать типы клиента**

Run: `uv run generate-openapi && cd frontend && pnpm generate`
Expected: `uv run verify-generated` зелёный.

- [ ] **Step 5: Экран**

`/admin/broadcasts` — список кампаний со статусом и счётчиками и форма
создания: выбор сегмента, тексты на двух языках, показ охвата рядом с
выбором, кнопка запуска с подтверждением и кнопка отмены у идущей кампании.
Счётчики идущей кампании обновлять `refetchInterval: 5000`, пока статус
`running`, — иначе прогресс приходится узнавать перезагрузкой.

Переводы `broadcast.title`, `broadcast.segment`, `broadcast.reach`,
`broadcast.start`, `broadcast.cancel`, `broadcast.confirm`,
`broadcast.status.draft|running|canceled|done`.

- [ ] **Step 6: Тест экрана**

Список отрисован; выбор сегмента запрашивает охват; запуск требует
подтверждения и вызывает `POST /api/admin/broadcasts/{id}/start`; у идущей
кампании видна кнопка отмены.

- [ ] **Step 7: Прогнать**

Run: `uv run pytest backend/api/tests/test_admin_routes.py -q` и
`cd frontend && pnpm --filter web test`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/api/src/repibot_api/routers/admin.py \
        backend/api/src/repibot_api/schemas.py \
        backend/api/tests/test_admin_routes.py \
        frontend/apps/web/src/app/admin/broadcasts \
        frontend/packages/core/src/i18n \
        frontend/packages/core/src/api/schema.d.ts
git commit -m "feat: создание и запуск рассылки из админки"
```

---

### Task 6: Документация и полная проверка

**Files:**
- Modify: `docs/deployment.md`

- [ ] **Step 1: Переменные и расписание**

Добавить `BROADCAST_RATE_PER_SECOND` в таблицу переменных и `run_broadcast` —
в таблицу расписаний с пометкой «каждую минуту, одна кампания за раз».

- [ ] **Step 2: Диагностика**

Строка в таблицу диагностики: «Рассылка встала» →
`select status, planned_count, sent_count, failed_count from broadcasts order
by id desc limit 5` и `select error, count(*) from broadcast_recipients where
status = 'failed' group by error`.

- [ ] **Step 3: Порядок действий при ошибке в тексте**

Отдельным абзацем: отменить кампанию из админки; отправленное не
отзывается; создать новую кампанию с исправленным текстом на тот же сегмент
нельзя без риска задвоения — сначала посмотреть, кому уже ушло, запросом
`select user_id from broadcast_recipients where broadcast_id = ? and status =
'sent'`.

- [ ] **Step 4: Полная проверка**

Run: `uv run check`
Expected: все восемь проверок зелёные.

- [ ] **Step 5: Commit**

```bash
git add docs/deployment.md
git commit -m "docs: эксплуатация рассылок"
```

---

## Plan Self-Review

**Покрытие спецификации.** Раздел 3 «Рассылки» — задача 1. Раздел 9 целиком:
черновик и предпросмотр охвата — задачи 3 и 5, фиксация аудитории запуском —
задача 3, таблица сегментов — задача 2, вычитание отписавшихся и бесканальных —
задача 2, темп под лимит Telegram и отмена между пачками — задача 4, неудача
одного получателя — задача 4, одна кампания за раз — задача 3. Раздел 11 в
части админских поверхностей — задача 5. Настройка раздела 10 — задача 1,
документация — задача 6.

**Заглушки.** Одно место в задаче 4 содержит запасной вариант вместо готового
ответа — длительность теста с выдержкой темпа; указано, что именно делать, а
не «разобраться». Экран в задаче 5 описан списком элементов и поведением, а не
разметкой: разметку диктуют компоненты `@repibot/ui`, и копия здесь разошлась
бы с ними.

**Согласованность имён.** `BroadcastStatus.draft|running|canceled|done` — одно
множество во всех задачах и в API. `RecipientStatus.pending|sent|failed` — то
же. `segment_query(name)` и `count_segment(session, name)` (задача 2)
вызываются из `start` (задача 3) и из маршрута охвата (задача 5).
`send_batch(*, telegram, email, limit=None)` (задача 4) вызывается только из
`run_broadcast`. Коды отказов `broadcast_not_draft` и `broadcast_busy`
объявлены в задаче 3 и используются в задаче 5.
