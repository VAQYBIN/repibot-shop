# Тикеты Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Человек пишет в поддержку из бота или из кабинета, персонал отвечает
в топике супергруппы, переписка одна и целиком лежит у нас.

**Architecture:** `tickets` и `ticket_messages` — источник истины. Каждое
сообщение пользователя уходит в топик супергруппы через outbox, каждое
сообщение сотрудника приходит вебхуком бота и превращается в сигнал
пользователю категории `service`. Топик создаётся при первом сообщении и
закрывается вместе с тикетом. Пустой `SUPPORT_CHAT_ID` выключает поддержку
целиком — стенд без супергруппы обязан подниматься.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async/PostgreSQL 18,
Alembic, aiogram 3, TaskIQ/Valkey, React 19, Next.js 16, TanStack Query v5,
TanStack Router, Vitest.

## Global Constraints

- План идёт после «Слоя доставки и согласия»: он опирается на
  `NotificationService.enqueue` и вид `ticket_reply` категории `service`.
- Ключ дедупликации сигнала об ответе — `ticket:{ticket_id}:msg:{message_id}`.
- `SUPPORT_CHAT_ID` пустой — клиентские и админские маршруты отвечают
  `support_unavailable`, бот не показывает `/support`, экраны скрыты.
- Лимиты: не больше `TICKET_MAX_OPEN` (умолчание 3) открытых тикетов на
  пользователя и не чаще одного сообщения в десять секунд. Ключ лимита — по
  пользователю, а не по IP: у бота IP один на всех.
- Сообщения уходят в Telegram без `parse_mode`, а в письме тело экранируется:
  чужой текст в топике не должен подделывать служебное сообщение.
- Сообщение из топика, для которого тикета нет, отбрасывается с записью в
  журнал. Сообщение от самого бота игнорируется — иначе ответ пользователя,
  пересланный в топик, вернулся бы ему же.
- Все комментарии и докстринги на русском и объясняют «почему».
- Каждая задача: сначала падающий тест, обязательно запущенный и увиденный
  красным, затем минимальная реализация, затем тематический commit на ветке
  `dev`. Полный `uv run check` — перед сдачей плана.
- Строки не длиннее 100 символов (ruff), переводы строк LF.

---

### Task 1: Модели переписки

**Files:**
- Create: `backend/core/src/repibot_core/db/models/support.py`
- Modify: `backend/core/src/repibot_core/db/models/__init__.py`
- Create: `backend/core/src/repibot_core/db/migrations/versions/0019_tickets.py`
- Create: `backend/core/tests/test_tickets.py`

**Interfaces:**
- Produces `TicketStatus` (`waiting_staff`, `waiting_user`, `closed`),
  `TicketAuthor` (`user`, `staff`, `system`),
  `Ticket(user_id, status, subject, telegram_topic_id, created_at, closed_at,
  last_user_message_at, last_staff_message_at)`,
  `TicketMessage(ticket_id, author_kind, author_user_id, author_telegram_id,
  body, telegram_message_id, created_at)`.
- Consumes голову миграций плана «Лесенка возврата» (`0018`). Если этот план
  исполняется раньше лесенки, поставить `down_revision` на реальную голову,
  которую покажет `uv run alembic heads`.

- [ ] **Step 1: Падающий тест**

`backend/core/tests/test_tickets.py`:

```python
"""Переписка с поддержкой: модели, сервис, лимиты."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Ticket, TicketAuthor, TicketMessage, TicketStatus, User

pytestmark = pytest.mark.docker


async def test_ticket_starts_waiting_for_staff(db_session: AsyncSession) -> None:
    """Статус называет, чьего хода ждём: это всё, что нужно и очереди, и человеку."""
    user = User(email=None, telegram_id=300_001, referral_code="ticket01")
    db_session.add(user)
    await db_session.flush()
    ticket = Ticket(user_id=user.id, status=TicketStatus.waiting_staff, subject="Не открывается")
    db_session.add(ticket)
    await db_session.flush()
    db_session.add(
        TicketMessage(ticket_id=ticket.id, author_kind=TicketAuthor.user, body="Не открывается")
    )
    await db_session.commit()

    stored = await db_session.scalar(select(TicketMessage))
    assert stored is not None
    assert stored.author_kind is TicketAuthor.user
    assert ticket.telegram_topic_id is None
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_tickets.py -q`
Expected: FAIL — `ImportError: cannot import name 'Ticket'`.

- [ ] **Step 3: Модели**

`backend/core/src/repibot_core/db/models/support.py`:

```python
"""Обращения в поддержку.

Переписка живёт здесь, а не в Telegram: у половины плательщиков Telegram не
привязан, и топик супергруппы для них — рабочее место персонала, а не канал
связи.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class TicketStatus(StrEnum):
    waiting_staff = "waiting_staff"
    waiting_user = "waiting_user"
    closed = "closed"


class TicketAuthor(StrEnum):
    user = "user"
    staff = "staff"
    system = "system"


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        # Очередь персонала — «что ждёт ответа дольше всех».
        Index("ix_tickets_queue", "status", "last_user_message_at"),
        Index("ix_tickets_user", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus, name="ticket_status"))
    subject: Mapped[str] = mapped_column(String(120))
    # Появляется после того, как топик создан в супергруппе. До этого момента
    # тикет уже существует: терять обращение из-за недоступного Telegram нельзя.
    telegram_topic_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_user_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_staff_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (Index("ix_ticket_messages_thread", "ticket_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    author_kind: Mapped[TicketAuthor] = mapped_column(Enum(TicketAuthor, name="ticket_author"))
    # У сотрудника, отвечающего из топика, нашего аккаунта может не быть.
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    body: Mapped[str] = mapped_column(Text)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Экспортировать все четыре имени из `db/models/__init__.py`.

- [ ] **Step 4: Миграция**

`0019_tickets.py` создаёт оба перечисления и обе таблицы с индексами
`ix_tickets_queue`, `ix_tickets_user`, `ix_ticket_messages_thread`. Форму
взять из соседней миграции, где уже создаются нативные перечисления
(`sa.Enum(..., name="...")` в `sa.Column`), чтобы `downgrade` тоже удалял тип.

- [ ] **Step 5: Прогнать**

Run: `uv run pytest backend/core/tests/test_tickets.py backend/core/tests/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/src/repibot_core/db/models/support.py \
        backend/core/src/repibot_core/db/models/__init__.py \
        backend/core/src/repibot_core/db/migrations/versions/0019_tickets.py \
        backend/core/tests/test_tickets.py
git commit -m "feat: модели обращений в поддержку"
```

---

### Task 2: Сервис переписки

**Files:**
- Create: `backend/core/src/repibot_core/services/support.py`
- Modify: `backend/core/src/repibot_core/settings.py`
- Modify: `backend/core/tests/test_tickets.py`

**Interfaces:**
- Produces `SupportService(session, settings=None)` с методами
  `open(user_id: int, body: str) -> Ticket`,
  `reply_from_user(user_id: int, ticket_id: int, body: str) -> TicketMessage`,
  `reply_from_staff(topic_id: int, body: str, *, telegram_id: int, message_id: int) -> TicketMessage | None`,
  `close(ticket_id: int, *, by_staff: bool) -> None`,
  `list_for_user(user_id: int) -> list[Ticket]`,
  `thread(ticket_id: int) -> list[TicketMessage]`;
  настройки `support_chat_id: int | None`, `ticket_max_open: int`.
- Consumes `NotificationService.enqueue`, `OutboxRepository.add`.

- [ ] **Step 1: Падающий тест лимита и потока**

```python
async def test_open_tickets_are_capped(db_session: AsyncSession) -> None:
    """Три открытых обращения — предел: у человека одновременно может сломаться
    оплата и доступ, но не десять вещей сразу."""
    user = User(email=None, telegram_id=300_002, referral_code="ticket02")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    service = SupportService(db_session)
    for index in range(3):
        await service.open(user.id, f"вопрос {index}")
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await service.open(user.id, "четвёртый")

    assert refusal.value.code == "too_many_tickets"


async def test_staff_reply_switches_the_turn_and_notifies(db_session: AsyncSession) -> None:
    """Ответ сотрудника обязан дойти до человека, а не остаться в топике."""
    user = User(email=None, telegram_id=300_003, referral_code="ticket03")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    service = SupportService(db_session)
    ticket = await service.open(user.id, "не открывается")
    ticket.telegram_topic_id = 555
    await db_session.commit()

    message = await service.reply_from_staff(
        555, "Проверьте профиль", telegram_id=777, message_id=42
    )
    await db_session.commit()

    assert message is not None
    assert ticket.status is TicketStatus.waiting_user
    kinds = list((await db_session.scalars(select(NotificationDelivery.kind))).all())
    assert kinds == ["ticket_reply"]


async def test_message_from_an_unknown_topic_is_dropped(db_session: AsyncSession) -> None:
    """Посторонняя тема в супергруппе не должна порождать переписку из воздуха."""
    assert await SupportService(db_session).reply_from_staff(
        999_999, "привет", telegram_id=777, message_id=1
    ) is None
```

Импорты: `NotificationDelivery`, `ServiceError`, `SupportService`.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_tickets.py -q`
Expected: FAIL — `ModuleNotFoundError: repibot_core.services.support`.

- [ ] **Step 3: Настройки**

В `settings.py`:

```python
    # Супергруппа с топиками. Пусто — поддержка выключена целиком: стенд без
    # супергруппы обязан подниматься и работать.
    support_chat_id: int | None = None
    ticket_max_open: int = Field(default=3, ge=1, le=20)
```

- [ ] **Step 4: Реализация**

`backend/core/src/repibot_core/services/support.py`. Ключевые решения,
которые обязаны быть в коде и в комментариях:

```python
"""Обращения в поддержку: одна переписка, два входа.

Внешние вызовы Telegram здесь не делаются: сервис пишет в базу и ставит
задачу в очередь. Иначе недоступная супергруппа теряла бы обращение, за
которое человек уже заплатил ожиданием.
"""

TOPIC_SUPPORT_OUTBOUND = "support.outbound"

# Тема топика — первые слова обращения: в списке тем супергруппы персонал
# должен различать обращения без открытия каждого.
SUBJECT_LIMIT = 120


class SupportService:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._outbox = OutboxRepository(session)

    def enabled(self) -> bool:
        return self._settings.support_chat_id is not None

    async def open(self, user_id: int, body: str) -> Ticket:
        self._require_enabled()
        text = body.strip()
        if not text:
            raise ServiceError("сообщение пустое", "validation_error")
        open_count = await self._session.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.user_id == user_id, Ticket.status != TicketStatus.closed)
        )
        if int(open_count or 0) >= self._settings.ticket_max_open:
            raise ServiceError("слишком много открытых обращений", "too_many_tickets")
        ticket = Ticket(
            user_id=user_id,
            status=TicketStatus.waiting_staff,
            subject=text[:SUBJECT_LIMIT],
            last_user_message_at=datetime.now(UTC),
        )
        self._session.add(ticket)
        await self._session.flush()
        await self._add_message(ticket, TicketAuthor.user, text, author_user_id=user_id)
        # Топика ещё нет: его создаст разбор очереди и вернёт идентификатор.
        await self._outbox.add(
            TOPIC_SUPPORT_OUTBOUND,
            {"ticket_id": ticket.id, "subject": ticket.subject, "body": text},
        )
        return ticket
```

Остальные методы по тому же образцу:

- `reply_from_user` — проверяет, что тикет принадлежит пользователю и не
  закрыт, добавляет сообщение, ставит `status = waiting_staff`,
  `last_user_message_at = now`, кладёт задачу `TOPIC_SUPPORT_OUTBOUND` с уже
  известным `ticket_id`.
- `reply_from_staff` — ищет тикет по `telegram_topic_id`; `None`, если не
  нашёлся, с `logger.warning` про посторонний топик. Иначе добавляет
  сообщение `TicketAuthor.staff`, ставит `status = waiting_user`,
  `last_staff_message_at = now` и вызывает
  `NotificationService(self._session).enqueue(user_id=ticket.user_id,
  kind="ticket_reply", dedup_key=f"ticket:{ticket.id}:msg:{message.id}",
  params={"body": body[:300]})`.
- `close(ticket_id, *, by_staff)` — ставит `closed`, `closed_at = now`,
  добавляет системное сообщение и кладёт в очередь задачу закрытия топика
  (`{"ticket_id": ..., "close": True}` той же темой).
- `list_for_user`, `thread` — простые выборки с сортировкой по времени.
- `_require_enabled` — бросает `ServiceError("поддержка недоступна",
  "support_unavailable")`, когда `support_chat_id` пуст.

- [ ] **Step 5: Прогнать**

Run: `uv run pytest backend/core/tests/test_tickets.py -q`
Expected: PASS. Для тестов установить `SUPPORT_CHAT_ID` через `monkeypatch`
и `get_settings.cache_clear()`, либо передавать `Settings` явно в
конструктор — второе предпочтительнее, оно не трогает глобальный кэш.

- [ ] **Step 6: Commit**

```bash
git add backend/core/src/repibot_core/services/support.py \
        backend/core/src/repibot_core/settings.py \
        backend/core/tests/test_tickets.py
git commit -m "feat: сервис переписки с поддержкой"
```

---

### Task 3: Топики супергруппы

**Files:**
- Create: `backend/core/src/repibot_core/integrations/telegram/support_chat.py`
- Modify: `backend/core/src/repibot_core/services/dispatcher.py`
- Modify: `backend/core/src/repibot_core/tasks.py`
- Create: `backend/core/tests/test_support_chat.py`

**Interfaces:**
- Produces `SupportChat(settings, client=None)` с методами
  `create_topic(name: str) -> int`, `post(topic_id: int, text: str) -> int`,
  `close_topic(topic_id: int) -> None`, `aclose() -> None`;
  обработчик темы `support.outbound` в диспетчере.
- Consumes `SupportService.TOPIC_SUPPORT_OUTBOUND`, `Ticket.telegram_topic_id`.

- [ ] **Step 1: Падающий тест клиента**

`backend/core/tests/test_support_chat.py` — на `httpx.MockTransport`, по
образцу `backend/core/tests/test_yookassa_client.py`:

```python
async def test_topic_is_created_once_and_reused() -> None:
    """Второй топик на то же обращение разорвал бы переписку надвое."""
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", maxsplit=1)[-1])
        return httpx.Response(200, json={"ok": True, "result": {"message_thread_id": 12}})

    chat = SupportChat(get_settings(), httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    topic_id = await chat.create_topic("Не открывается")

    assert topic_id == 12
    assert calls == ["createForumTopic"]
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/core/tests/test_support_chat.py -q`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Клиент**

`support_chat.py` — три метода поверх Bot API: `createForumTopic` с
`chat_id` и `name`, `sendMessage` с `chat_id`, `message_thread_id` и `text`
(без `parse_mode`: текст пользователя не должен становиться разметкой),
`closeForumTopic` с `chat_id` и `message_thread_id`. Ответ проверяется на
`ok: true`, иначе бросается `RuntimeError` с телом ответа — разбор очереди
превратит его в отложенную попытку.

- [ ] **Step 4: Обработчик очереди**

В `dispatcher.py` добавить параметр `support: SupportChat | None = None` и
регистрацию:

```python
    async def handle_support_outbound(payload: dict[str, object]) -> None:
        """Доводит сообщение до топика, создавая топик при первой необходимости.

        Идентификатор топика записывается своей транзакцией сразу после
        создания: падение на отправке не должно приводить ко второму топику
        при повторе.
        """
        if support is None:
            msg = "супергруппа поддержки не передана диспетчеру"
            raise RuntimeError(msg)
        ticket_id = int(str(payload["ticket_id"]))
        async with session_factory() as session:
            ticket = await session.get(Ticket, ticket_id)
            if ticket is None:
                return
            if ticket.telegram_topic_id is None:
                ticket.telegram_topic_id = await support.create_topic(ticket.subject)
                await session.commit()
            topic_id = ticket.telegram_topic_id
            closing = bool(payload.get("close"))
        if closing:
            await support.close_topic(topic_id)
            return
        await support.post(topic_id, str(payload["body"]))

    dispatcher.register(TOPIC_SUPPORT_OUTBOUND, handle_support_outbound)
```

- [ ] **Step 5: Сборка в задаче**

В `tasks.py`, в `process_outbox`, собрать `SupportChat` рядом с `BotApi`,
только если `support_chat_id` задан, закрыть его в `finally` и передать в
`_dispatcher`. Пустая настройка означает, что обработчик не регистрируется, и
сообщения темы `support.outbound` просто не появляются.

- [ ] **Step 6: Прогнать**

Run: `uv run pytest backend/core/tests/test_support_chat.py backend/core/tests/test_tickets.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/core/src/repibot_core/integrations/telegram/support_chat.py \
        backend/core/src/repibot_core/services/dispatcher.py \
        backend/core/src/repibot_core/tasks.py \
        backend/core/tests/test_support_chat.py
git commit -m "feat: обращение доходит до топика супергруппы"
```

---

### Task 4: Бот — обе стороны разговора

**Files:**
- Create: `backend/bot/src/repibot_bot/handlers/support.py`
- Modify: `backend/bot/src/repibot_bot/main.py`
- Modify: `backend/core/src/repibot_core/i18n.py`
- Create: `backend/bot/tests/test_support_handlers.py` (директорию тестов бота
  создать, если её нет; расположение и фикстуры повторить за
  `backend/core/tests`)

**Interfaces:**
- Produces роутер `build_support_router()`, обрабатывающий `/support`,
  `/close`, сообщение пользователя в личке при открытом тикете и сообщение
  сотрудника в топике супергруппы.
- Consumes `SupportService.open`, `reply_from_user`, `reply_from_staff`, `close`.

- [ ] **Step 1: Падающий тест «эхо не возвращается»**

```python
async def test_bot_own_message_in_the_topic_is_ignored() -> None:
    """Наше же сообщение, пересланное в топик, не должно вернуться человеку.

    Без этой проверки каждая реплика пользователя приходила бы ему обратно
    как ответ поддержки — и переписка зациклилась бы.
    """
```

Тест собирает `Message` aiogram с `from_user.is_bot = True` и проверяет, что
`SupportService.reply_from_staff` не вызывался (подменить сервис двойником).

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/bot/tests/test_support_handlers.py -q`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Роутер**

`handlers/support.py` — четыре обработчика:

- `/support` в личке: если у человека есть открытый тикет, показать его номер
  и предложить писать прямо в диалог; иначе — попросить описать проблему и
  создать тикет следующим сообщением через FSM или сразу по тексту команды.
- Обычное сообщение в личке при наличии открытого тикета —
  `reply_from_user`. Без открытого тикета — подсказка про `/support`, чтобы
  случайное сообщение не создавало обращение.
- Сообщение в супергруппе с `message_thread_id`: пропустить, если
  `message.from_user.is_bot`, иначе `reply_from_staff(topic_id, text,
  telegram_id=..., message_id=...)`.
- `/close` в топике: `close(ticket_id, by_staff=True)`.

Фильтр по чату: обработчики супергруппы срабатывают только при
`message.chat.id == settings.support_chat_id`.

- [ ] **Step 4: Тексты**

В `i18n.py` добавить `ticket.reply.bot`, `ticket.reply.subject`,
`ticket.reply.body`, `bot.support.opened`, `bot.support.ask`,
`bot.support.no_open`, `bot.support.closed`. Русский текст ответа:
«Поддержка ответила:\n\n{body}».

- [ ] **Step 5: Регистрация**

В `backend/bot/src/repibot_bot/main.py` включить
`dispatcher.include_router(build_support_router())` — и только если
`support_chat_id` задан, иначе команда `/support` не должна существовать.

- [ ] **Step 6: Прогнать**

Run: `uv run pytest backend/bot/tests -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/bot/src/repibot_bot/handlers/support.py \
        backend/bot/src/repibot_bot/main.py \
        backend/core/src/repibot_core/i18n.py \
        backend/bot/tests/test_support_handlers.py
git commit -m "feat: поддержка в боте — обращение и ответ из топика"
```

---

### Task 5: Клиентское API и экраны

**Files:**
- Create: `backend/api/src/repibot_api/routers/support.py`
- Modify: `backend/api/src/repibot_api/schemas.py`, `backend/api/src/repibot_api/main.py`
- Create: `backend/api/tests/test_support_routes.py`
- Create: `frontend/packages/core/src/support/hooks.tsx`, `.../support/hooks.test.tsx`
- Modify: `frontend/packages/core/src/index.ts`, `frontend/packages/core/src/i18n/ru.ts`, `.../en.ts`
- Create: `frontend/apps/web/src/app/account/support/page.tsx` и `page.test.tsx`
- Modify: `frontend/apps/web/src/components/account-shell.tsx:13-18`
- Create: `frontend/apps/miniapp/src/routes/support.tsx` и `support.test.tsx`
- Modify: `frontend/apps/miniapp/src/router.tsx`, `frontend/apps/miniapp/src/routes/root.tsx`

**Interfaces:**
- Produces `GET /api/support/tickets`, `POST /api/support/tickets`,
  `GET /api/support/tickets/{id}`, `POST /api/support/tickets/{id}/messages`,
  `POST /api/support/tickets/{id}/close`; хуки `useTickets()`,
  `useTicket(id)`, `useOpenTicket()`, `useReplyToTicket(id)`.
- Consumes `SupportService` из задачи 2, `RateLimiter` из
  `repibot_core.ratelimit`.

- [ ] **Step 1: Падающий тест маршрутов**

```python
async def test_ticket_round_trip(api_client: AsyncClient, user_headers: dict[str, str]) -> None:
    created = await api_client.post(
        "/api/support/tickets", headers=user_headers, json={"body": "не открывается"}
    )
    listed = await api_client.get("/api/support/tickets", headers=user_headers)

    assert created.status_code == 201
    assert [item["status"] for item in listed.json()] == ["waiting_staff"]


async def test_support_is_off_without_a_supergroup(
    api_client: AsyncClient, user_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Стенд без супергруппы обязан подниматься и честно отвечать отказом."""
    monkeypatch.delenv("SUPPORT_CHAT_ID", raising=False)
    get_settings.cache_clear()

    response = await api_client.post(
        "/api/support/tickets", headers=user_headers, json={"body": "привет"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "support_unavailable"
    get_settings.cache_clear()
```

Код `support_unavailable` добавить в словарь соответствий в
`backend/api/src/repibot_api/errors.py` со значением 409.

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/api/tests/test_support_routes.py -q`
Expected: FAIL — 404.

- [ ] **Step 3: Маршруты**

`routers/support.py` — пять маршрутов из блока Interfaces, каждый под
`current_context`. Перед созданием тикета и перед добавлением сообщения —
проверка частоты через `RateLimiter(redis).hit(f"ticket:{user_id}", Rule(...))`
с окном в 10 секунд и одним разрешённым обращением; правило объявить рядом
с `LETTER_PER_EMAIL` в `repibot_core/ratelimit.py` под именем
`TICKET_MESSAGE_PER_USER`.

Схемы: `TicketResponse(id, status, subject, created_at, last_staff_message_at)`,
`TicketThreadResponse(ticket, messages)`,
`TicketMessageResponse(id, author, body, created_at)`,
`OpenTicketRequest(body)`, `TicketReplyRequest(body)`.

- [ ] **Step 4: Пересобрать типы клиента**

Run: `uv run generate-openapi && cd frontend && pnpm generate`
Expected: `uv run verify-generated` зелёный.

- [ ] **Step 5: Хуки и экраны**

`frontend/packages/core/src/support/hooks.tsx` — четыре хука по образцу
`payments/hooks.tsx`. У `useTicket(id)` — `refetchOnWindowFocus: 'always'` и
`refetchInterval: 15_000`, пока `status === 'waiting_staff'`: человек ждёт
ответа и не должен перезагружать страницу, чтобы его увидеть.

Экран кабинета `/account/support`: список обращений, форма нового,
переписка выбранного. Ссылка в `LINKS` в `account-shell.tsx`:

```tsx
  { href: '/account/support', key: 'support.title' },
```

Экран Mini App `routes/support.tsx` — та же логика на компонентах
`@repibot/ui`; маршрут добавить в `router.tsx` и ссылку в `Navigation` в
`routes/root.tsx`.

Переводы `support.title`, `support.new`, `support.send`, `support.empty`,
`support.waiting_staff`, `support.waiting_user`, `support.closed`,
`support.unavailable` в `ru.ts` и `en.ts`.

- [ ] **Step 6: Тесты экранов**

`page.test.tsx` и `support.test.tsx`: пустой список показывает приглашение,
отправка формы вызывает `POST /api/support/tickets`, ответ поддержки виден в
переписке, при `support_unavailable` показывается объяснение, а форма скрыта.

- [ ] **Step 7: Прогнать**

Run: `uv run pytest backend/api/tests/test_support_routes.py -q` и
`cd frontend && pnpm test`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/api/src/repibot_api/routers/support.py \
        backend/api/src/repibot_api/schemas.py \
        backend/api/src/repibot_api/main.py \
        backend/api/src/repibot_api/errors.py \
        backend/core/src/repibot_core/ratelimit.py \
        backend/api/tests/test_support_routes.py \
        frontend/packages/core/src/support \
        frontend/packages/core/src/index.ts \
        frontend/packages/core/src/i18n \
        frontend/packages/core/src/api/schema.d.ts \
        frontend/apps/web/src/app/account/support \
        frontend/apps/web/src/components/account-shell.tsx \
        frontend/apps/miniapp/src/routes/support.tsx \
        frontend/apps/miniapp/src/routes/support.test.tsx \
        frontend/apps/miniapp/src/router.tsx \
        frontend/apps/miniapp/src/routes/root.tsx
git commit -m "feat: поддержка в кабинете и Mini App"
```

---

### Task 6: Админский экран тикетов

**Files:**
- Modify: `backend/api/src/repibot_api/routers/admin.py`
- Modify: `backend/api/tests/test_admin_routes.py`
- Create: `frontend/apps/web/src/app/admin/tickets/page.tsx` и `page.test.tsx`

**Interfaces:**
- Produces `GET /api/admin/tickets`, `GET /api/admin/tickets/{id}`,
  `POST /api/admin/tickets/{id}/messages`, `POST /api/admin/tickets/{id}/close`
  под `require_role(UserRole.support, UserRole.admin)`.
- Consumes `SupportService`, `audit_log`.

- [ ] **Step 1: Падающий тест ролей**

```python
async def test_support_role_sees_tickets_but_not_plans(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Роль поддержки не должна дотягиваться до тарифов и денег."""
    tickets = await api_client.get("/api/admin/tickets", headers=support_headers)
    plans = await api_client.post(
        "/api/admin/plans", headers=support_headers, json={"code": "x"}
    )

    assert tickets.status_code == 200
    assert plans.status_code == 403
```

- [ ] **Step 2: Запустить и увидеть падение**

Run: `uv run pytest backend/api/tests/test_admin_routes.py -k support_role_sees -q`
Expected: FAIL — 404 на списке тикетов.

- [ ] **Step 3: Маршруты**

Добавить четыре маршрута в `admin.py`. Ответ сотрудника из админки идёт тем
же путём, что и из топика: `SupportService.reply_from_staff` по
`ticket.telegram_topic_id`, если он есть, иначе — отдельный метод
`reply_from_admin(ticket_id, body, *, author_user_id)`, ставящий и сообщение,
и сигнал пользователю. Каждое действие писать в `audit_log` тем же способом,
что и соседние админские операции.

- [ ] **Step 4: Экран**

`/admin/tickets` — список с фильтром по статусу и переписка выбранного
обращения с формой ответа. Тест экрана: список отрисован, отправка формы
вызывает `POST /api/admin/tickets/{id}/messages`.

- [ ] **Step 5: Прогнать**

Run: `uv run pytest backend/api/tests/test_admin_routes.py -q` и
`cd frontend && pnpm --filter web test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/src/repibot_api/routers/admin.py \
        backend/api/tests/test_admin_routes.py \
        frontend/apps/web/src/app/admin/tickets
git commit -m "feat: тикеты в админке для роли поддержки"
```

---

### Task 7: Документация и сквозной сценарий

**Files:**
- Modify: `docs/deployment.md`

- [ ] **Step 1: Инструкция по супергруппе**

Описать шаги: создать супергруппу, включить в ней темы (Topics), добавить
бота администратором с правом управления темами, взять идентификатор чата
(он отрицательный и начинается с `-100`) и положить в `SUPPORT_CHAT_ID`.
Отдельно предупредить: без права управления темами `createForumTopic`
возвращает ошибку, и обращения зависают в очереди.

- [ ] **Step 2: Переменные и диагностика**

Добавить `SUPPORT_CHAT_ID` и `TICKET_MAX_OPEN` в таблицу переменных. В
таблицу диагностики — строку «Обращения не появляются в супергруппе» →
`select topic, last_error from outbox where topic = 'support.outbound' and
processed_at is null`.

- [ ] **Step 3: Полная проверка**

Run: `uv run check`
Expected: все восемь проверок зелёные.

- [ ] **Step 4: Commit**

```bash
git add docs/deployment.md
git commit -m "docs: настройка супергруппы поддержки"
```

---

## Plan Self-Review

**Покрытие спецификации.** Раздел 3 «Тикеты» — задача 1. Раздел 8 целиком:
два входа — задачи 4 и 5, топики и их закрытие — задачи 3 и 4, выключение
поддержки пустой настройкой — задачи 2, 4 и 5, лимиты — задачи 2 и 5, роль
`support` — задача 6. Раздел 11 в части клиентских и админских поверхностей —
задачи 5 и 6. Раздел 12 в части эха от бота и постороннего топика — задачи 2
и 4. Настройки раздела 10 — задача 2, документация — задача 7.

**Заглушки.** В задачах 2, 4, 5 и 6 часть методов и экранов описана образцом
и списком решений, а не готовым кодом. Это сделано осознанно: там повторяется
уже написанная в этом же плане форма (например, `reply_from_user` — это
`open` без создания тикета), и копия кода в плане разошлась бы с оригиналом
после первой же правки. Каждое такое место называет точный образец в
репозитории.

**Согласованность имён.** `TicketStatus.waiting_staff` — единственное
начальное состояние во всех задачах. `TOPIC_SUPPORT_OUTBOUND =
"support.outbound"` объявлен в задаче 2 и используется в задачах 3 и 7.
`SupportChat.create_topic/post/close_topic` (задача 3) вызываются только из
обработчика очереди. Вид `ticket_reply` совпадает с реестром `_KINDS` плана
«Слой доставки», его `text_key` — `ticket.reply` — с ключами i18n задачи 4.
`support_unavailable` — один код отказа в сервисе, API и обоих клиентах.
