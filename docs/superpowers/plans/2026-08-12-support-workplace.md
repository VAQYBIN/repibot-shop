# Рабочее место поддержки — план реализации

> **Для исполнителей:** задачи выполняются по одной, каждая заканчивается зелёными тестами. Шаги отмечены галочками (`- [ ]`).

**Цель:** превратить тему супергруппы из ленты сообщений в рабочее место: состояние обращения видно из списка тем, собеседник — из карточки, управление — из семи команд.

**Устройство:** метка состояния хранится в `tickets.topic_status_mark` и сравнивается с настоящим статусом при разборе очереди, поэтому Bot API дёргается только на переходах. Карточку собирает модуль, ничего не знающий про Telegram. Блокировка и заглушение живут в отдельном сервисе, чтобы бот, админка и будущие входы звали одно и то же.

**Основание:** `docs/superpowers/specs/2026-08-12-support-workplace-design.md`

**Стек:** Python 3.13, SQLAlchemy 2 async, Alembic, aiogram 3, TaskIQ, pytest.

## Общие ограничения

Действуют в каждой задаче, повторно не оговариваются:

- Комментарии и строки документации по-русски, объясняют **почему**, а не что.
- TDD: тест пишется первым и обязан упасть по названной причине до реализации.
- mypy strict, ruff line-length 100, окончания строк LF.
- Тексты для персонала — русские прямо в коде рядом с обработчиком. Тексты для человека — оба языка в `i18n.py`.
- **Агент не выполняет команд git.** Коммиты делает ведущий между волнами.
- **Агент не запускает `uv run check` целиком** и не форматирует пакет целиком: только свои тесты и `ruff format` по своим файлам.
- **Агент не трогает файлы вне своего списка.** Общие файлы уже подготовлены задачей 1.
- Тесты ядра и API идут против настоящего Postgres в контейнере: помечать `pytestmark = pytest.mark.docker`, брать фикстуру `db_session` из корневого `conftest.py`.
- Супергруппа в тестах не поднимается: `SupportChat` подменяется двойником, считающим вызовы.

## Порядок волн

| Волна | Задачи | Почему вместе |
|---|---|---|
| — | 1 | Общие файлы: миграция, модели, тексты, коды ошибок, чистые функции имени темы |
| 1 | 2, 3, 4 | Три новых файла, ни одного общего |
| 2 | 5, 6 | `support.py` и пара `support_chat.py` + `dispatcher.py` — разные руки |
| 3 | 7, 8 | Команды бота зависят от задач 4–6; документация — от всего |

## Файлы

**Создаются:**
- `backend/core/src/repibot_core/db/migrations/versions/0019_support_workplace.py`
- `backend/core/src/repibot_core/services/support_card.py` — сборка карточки собеседника
- `backend/core/src/repibot_core/services/moderation.py` — бан, разбан, заглушение
- `backend/core/tests/test_support_card.py`
- `backend/core/tests/test_moderation.py`

**Изменяются:**
- `backend/core/src/repibot_core/db/models/support.py`, `db/models/user.py` — по колонке
- `backend/core/src/repibot_core/services/support.py` — метки, уведомление о закрытии, запрет заглушённому
- `backend/core/src/repibot_core/services/notifications.py` — вид `ticket_closed`
- `backend/core/src/repibot_core/services/dispatcher.py` — новый порядок разбора темы
- `backend/core/src/repibot_core/integrations/telegram/support_chat.py` — переименование темы
- `backend/core/src/repibot_core/tasks.py` — пробуждение очереди, устройства диспетчеру
- `backend/core/src/repibot_core/i18n.py` — тексты закрытия и отказов
- `backend/api/src/repibot_api/errors.py` — код `support_muted`
- `backend/api/src/repibot_api/routers/support.py`, `routers/admin.py` — пробуждение очереди
- `backend/bot/src/repibot_bot/handlers/support.py` — семь команд
- `backend/bot/src/repibot_bot/middleware.py` — обрыв на заблокированном, фасад устройств
- `docs/deployment.md` — раздел про рабочее место

---

### Задача 1: Основа данных и общие значения

**Исполняет ведущий до первой волны.**

**Файлы:**
- Создать: `backend/core/src/repibot_core/db/migrations/versions/0019_support_workplace.py`
- Изменить: `db/models/support.py`, `db/models/user.py`, `services/support.py`, `services/notifications.py`, `i18n.py`, `backend/api/src/repibot_api/errors.py`

**Отдаёт следующим задачам:**
- `Ticket.topic_status_mark: TicketStatus | None`
- `User.support_muted_at: datetime | None`
- `repibot_core.services.support.topic_name(ticket: Ticket) -> str`
- `repibot_core.services.support.TOPIC_MARKS: dict[TicketStatus, str]`
- вид уведомления `ticket_closed`
- ключи текстов `ticket.closed.{subject,body,bot}`, `bot.support.muted`, `bot.blocked`
- код ошибки `support_muted` → 403

- [ ] **Шаг 1: Колонка состояния темы**

В `db/models/support.py`, в классе `Ticket`, после `telegram_topic_id`:

```python
    # Метка состояния, которая сейчас стоит в названии темы. Пустая означает
    # две вещи разом: тема ещё не помечена и карточка собеседника в неё не
    # уходила — второго признака не нужно, они появляются вместе.
    topic_status_mark: Mapped[TicketStatus | None] = mapped_column(
        Enum(TicketStatus, name="ticket_status")
    )
```

- [ ] **Шаг 2: Колонка заглушения**

В `db/models/user.py`, рядом с `marketing_opt_out_at`:

```python
    # Момент, а не флаг, по той же причине, что и отказ от рассылок: при
    # разборе жалобы важно, когда человеку закрыли поддержку.
    support_muted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Шаг 3: Миграция**

```python
"""Рабочее место поддержки: метка состояния темы и заглушение.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_type=False: перечисление статусов создано миграцией 0017, и
    # повторное создание оборвало бы обновление на живой базе.
    status = postgresql.ENUM(name="ticket_status", create_type=False)
    op.add_column("tickets", sa.Column("topic_status_mark", status, nullable=True))
    op.add_column(
        "users", sa.Column("support_muted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "support_muted_at")
    op.drop_column("tickets", "topic_status_mark")
```

- [ ] **Шаг 4: Имя темы**

В `services/support.py`, после `SUBJECT_LIMIT`:

```python
# Метка состояния в названии темы: очередь работы читается по цвету, без
# чтения слов. Красное ждёт нас, жёлтое ждёт человека, галочка закрыта.
TOPIC_MARKS: dict[TicketStatus, str] = {
    TicketStatus.waiting_staff: "🔴",
    TicketStatus.waiting_user: "🟡",
    TicketStatus.closed: "✅",
}

# Предел Bot API на имя темы. Тема обращения хранится длиннее (SUBJECT_LIMIT),
# и с меткой и номером имя иначе перестало бы приниматься.
TOPIC_NAME_LIMIT = 128


def topic_name(ticket: Ticket) -> str:
    """Название темы: метка состояния, номер обращения, сама тема."""
    return f"{TOPIC_MARKS[ticket.status]} #{ticket.id} {ticket.subject}"[:TOPIC_NAME_LIMIT]
```

- [ ] **Шаг 5: Вид уведомления о закрытии**

В `services/notifications.py`, в кортеже `_KINDS`, сразу после `ticket_reply`:

```python
        NotificationKind(
            "ticket_closed", NotificationCategory.service, "ticket.closed", "/account/support"
        ),
```

- [ ] **Шаг 6: Тексты**

В `i18n.py`, в русский словарь рядом с `ticket.reply.*`:

```python
        "ticket.closed.subject": "Обращение закрыто",
        "ticket.closed.body": (
            "Обращение №{id} закрыто. Если вопрос остался — откройте новое, "
            "переписка сохранится."
        ),
        "ticket.closed.bot": (
            "Обращение №{id} закрыто. Если вопрос остался — откройте новое."
        ),
        "bot.support.muted": "Доступ к поддержке ограничен.",
        "bot.blocked": "Аккаунт заблокирован.",
```

В английский:

```python
        "ticket.closed.subject": "Ticket closed",
        "ticket.closed.body": (
            "Ticket #{id} is closed. If the question stands, open a new one — "
            "the thread is kept."
        ),
        "ticket.closed.bot": "Ticket #{id} is closed. If the question stands, open a new one.",
        "bot.support.muted": "Support access is restricted.",
        "bot.blocked": "The account is blocked.",
```

- [ ] **Шаг 7: Код ошибки**

В `backend/api/src/repibot_api/errors.py`, в `_SERVICE_STATUS`, рядом с `support_unavailable`:

```python
    "support_muted": status.HTTP_403_FORBIDDEN,
```

- [ ] **Шаг 8: Проверка**

```
uv run pytest backend/core/tests/test_migrations.py backend/core/tests/test_notifications.py backend/core/tests/test_tickets.py -q
uv run mypy backend
```
Ожидание: зелено. Тест «у каждого вида уведомления есть тексты» покрывает шаги 5–6 сам.

---

### Задача 2: Карточка собеседника

**Волна 1. Файлы этой задачи не пересекаются ни с чем.**

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/support_card.py`
- Тест: `backend/core/tests/test_support_card.py`

**Потребляет:** `Ticket.topic_status_mark`, `User.support_muted_at` (задача 1).

**Отдаёт:**

```python
async def build_card(
    session: AsyncSession, ticket: Ticket, *, devices: tuple[int, int] | None
) -> str: ...

async def devices_for_card(
    session: AsyncSession, panel: PanelDevices, user_id: int
) -> tuple[int, int] | None: ...
```

`devices` — пара «привязано, лимит»; `None` означает «панель не ответила» и печатается как «н/д».

**Запрещено:** трогать `dispatcher.py`, `support.py`, хендлеры бота — карточку подключат задачи 6 и 7.

- [ ] **Шаг 1: Тест на полную карточку**

`backend/core/tests/test_support_card.py`:

```python
"""Карточка собеседника: всё, что помогает решить вопрос, одним сообщением."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import (
    Plan,
    Subscription,
    SubscriptionSource,
    Ticket,
    TicketStatus,
    User,
)
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.support_card import build_card

pytestmark = pytest.mark.docker


async def _plan(session: AsyncSession, code: str) -> Plan:
    plan = Plan(
        code=code,
        name={"ru": "Год", "en": "Year"},
        description=None,
        duration_days=365,
        price_rub=Decimal("1990.00"),
        price_stars=1990,
        hwid_device_limit=5,
        internal_squad_uuids=[],
    )
    session.add(plan)
    await session.flush()
    return plan


async def test_card_names_the_person_and_their_subscription(db_session: AsyncSession) -> None:
    """Сотрудник должен узнать собеседника, не открывая админку."""
    user = User(
        email="ivan@example.com",
        email_verified_at=datetime.now(UTC),
        telegram_id=513_442_219,
        telegram_username="ivan",
        name="Иван",
        referral_code="card0001",
    )
    db_session.add(user)
    await db_session.flush()
    plan = await _plan(db_session, "card-year")
    db_session.add(
        Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionState.active,
            started_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=83),
            auto_renew_enabled=True,
            source=SubscriptionSource.purchase,
        )
    )
    ticket = Ticket(user_id=user.id, status=TicketStatus.waiting_staff, subject="Не открывается")
    db_session.add(ticket)
    await db_session.commit()

    card = await build_card(db_session, ticket, devices=(3, 5))

    assert "Иван" in card
    assert f"#{ticket.id}" in card
    assert "@ivan" in card
    assert "513442219" in card
    assert "ivan@example.com" in card
    assert "Год" in card
    assert "83" in card
    assert "3 из 5" in card
    assert "/close_silent" in card
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```
uv run pytest backend/core/tests/test_support_card.py -q
```
Ожидание: `ModuleNotFoundError: repibot_core.services.support_card`.

- [ ] **Шаг 3: Реализация**

`backend/core/src/repibot_core/services/support_card.py`:

```python
"""Карточка собеседника для темы поддержки.

Модуль ничего не знает про Telegram и отдаёт готовый текст: так его можно
проверить тестом без супергруппы, а звать — и из разбора очереди, и из
команды `/info`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import Plan, Subscription, Ticket, User, UserStatus
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.integrations.remnawave.devices import PanelDevices

logger = logging.getLogger(__name__)

# Команды перечислены в самой карточке: рабочий чат — единственное место, где
# сотрудник о них узнаёт, а справки в интерфейсе у него нет.
COMMANDS = "Команды: /info /close /close_silent /mute /unmute /ban /unban"

DATE_FORMAT = "%d.%m.%Y"


async def build_card(
    session: AsyncSession, ticket: Ticket, *, devices: tuple[int, int] | None
) -> str:
    """Текст карточки. Отсутствующие сведения не показываются пустыми строками."""
    user = await UserRepository(session).get(ticket.user_id)
    if user is None:
        # Обращение живёт только вместе с аккаунтом, но разбор очереди может
        # застать удаление: карточка без собеседника лучше упавшей задачи.
        return f"👤 Аккаунт удалён · обращение #{ticket.id}\n\n{COMMANDS}"

    lines = [_head(user, ticket), _telegram(user)]
    email = _email(user)
    if email is not None:
        lines.append(email)
    subscription = await SubscriptionRepository(session).get_for_user(user.id)
    plan = (
        await PlanRepository(session).get(subscription.plan_id)
        if subscription is not None
        else None
    )
    lines.extend(_subscription(subscription, plan))
    lines.append(_devices(devices))
    lines.append(f"С нами с {user.created_at.strftime(DATE_FORMAT)}")
    lines.extend(_restrictions(user))
    return "\n".join(lines) + f"\n\n{COMMANDS}"


async def devices_for_card(
    session: AsyncSession, panel: PanelDevices, user_id: int
) -> tuple[int, int] | None:
    """Привязанные устройства и лимит тарифа.

    Отказ панели гасится здесь: карточка без числа устройств хуже карточки с
    ним, но несозданная тема хуже обеих.
    """
    user = await UserRepository(session).get(user_id)
    if user is None or user.remnawave_id is None:
        return None
    subscription = await SubscriptionRepository(session).get_for_user(user_id)
    if subscription is None:
        return None
    plan = await PlanRepository(session).get(subscription.plan_id)
    try:
        found = await panel.list(user.remnawave_id)
    except Exception:  # noqa: BLE001 — отказ панели любой природы не должен рвать тему
        logger.warning("панель не ответила о устройствах", extra={"user_id": user_id})
        return None
    return len(found), plan.hwid_device_limit if plan is not None else 0


def _head(user: User, ticket: Ticket) -> str:
    name = user.name or "Без имени"
    return f"👤 {name} · обращение #{ticket.id}"


def _telegram(user: User) -> str:
    if user.telegram_id is None:
        return "Telegram: не привязан"
    if user.telegram_username:
        return f"Telegram: @{user.telegram_username} ({user.telegram_id})"
    return f"Telegram: {user.telegram_id}"


def _email(user: User) -> str | None:
    if user.email is None:
        return None
    mark = "✓" if user.email_verified_at is not None else "✉ не подтверждена"
    return f"Почта: {user.email} {mark}"


def _subscription(subscription: Subscription | None, plan: Plan | None) -> list[str]:
    if subscription is None:
        return ["Подписка: не покупал"]
    title = plan.name.get("ru", plan.code) if plan is not None else "неизвестный тариф"
    days = (subscription.expires_at - datetime.now(UTC)).days
    if days >= 0:
        when = f"активна до {subscription.expires_at.strftime(DATE_FORMAT)} (осталось {days} дн.)"
    else:
        when = f"истекла {subscription.expires_at.strftime(DATE_FORMAT)} ({-days} дн. назад)"
    renew = "включено" if subscription.auto_renew_enabled else "выключено"
    return [f"Тариф: {title} · {when}", f"Автопродление: {renew}"]


def _devices(devices: tuple[int, int] | None) -> str:
    if devices is None:
        return "Устройства: н/д"
    used, limit = devices
    return f"Устройства: {used} из {limit}"


def _restrictions(user: User) -> list[str]:
    """Ограничения показываются явно: иначе непонятно, почему человек молчит."""
    lines = []
    if user.status is UserStatus.banned:
        lines.append("⛔ Заблокирован")
    if user.support_muted_at is not None:
        lines.append("🔇 Поддержка закрыта")
    return lines
```

- [ ] **Шаг 4: Тест проходит**

```
uv run pytest backend/core/tests/test_support_card.py -q
```

- [ ] **Шаг 5: Тесты на бедные случаи**

Дописать в тот же файл: пользователь без Telegram («не привязан»), без почты (строки нет), без подписки («не покупал»), с истёкшей подпиской («истекла», «дн. назад»), `devices=None` («н/д»), заблокированный («⛔»), заглушённый («🔇»). Каждый — отдельная функция с строкой документации, объясняющей, зачем сотруднику эта строка.

- [ ] **Шаг 6: Тест на отказ панели**

```python
class _DeadPanel:
    """Панель, которая не отвечает. Карточка обязана пережить её молчание."""

    async def list(self, panel_id: int) -> list[object]:
        msg = "панель недоступна"
        raise RuntimeError(msg)


async def test_dead_panel_leaves_the_card_without_devices(db_session: AsyncSession) -> None:
    user = User(email=None, telegram_id=513_000_101, remnawave_id=77, referral_code="card0009")
    db_session.add(user)
    await db_session.commit()

    assert await devices_for_card(db_session, _DeadPanel(), user.id) is None  # type: ignore[arg-type]
```

- [ ] **Шаг 7: Итог**

```
uv run pytest backend/core/tests/test_support_card.py -q
uv run ruff format backend/core/src/repibot_core/services/support_card.py backend/core/tests/test_support_card.py
uv run ruff check backend/core/src/repibot_core/services/support_card.py backend/core/tests/test_support_card.py
uv run mypy backend/core/src/repibot_core/services/support_card.py
```

---

### Задача 3: Блокировка и заглушение

**Волна 1.**

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/moderation.py`
- Тест: `backend/core/tests/test_moderation.py`

**Потребляет:** `User.support_muted_at` (задача 1), `AuditRepository.record` (существует).

**Отдаёт:**

```python
class ModerationService:
    def __init__(self, session: AsyncSession) -> None: ...
    async def ban(self, user_id: int, *, actor_id: int | None) -> bool: ...
    async def unban(self, user_id: int, *, actor_id: int | None) -> bool: ...
    async def mute_support(self, user_id: int, *, actor_id: int | None) -> bool: ...
    async def unmute_support(self, user_id: int, *, actor_id: int | None) -> bool: ...
```

Возвращается признак «состояние изменилось»: повтор ничего не делает и не пишет в журнал, а вызывающий отвечает «уже заблокирован» вместо ложного подтверждения.

**Запрещено:** трогать `support.py`, `middleware.py`, хендлеры — проверки подключат задачи 5 и 7.

- [ ] **Шаг 1: Тест на бан**

`backend/core/tests/test_moderation.py`:

```python
"""Блокировка аккаунта и заглушение поддержки."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import AuditLog, User, UserRole, UserStatus
from repibot_core.services.errors import ServiceError
from repibot_core.services.moderation import ModerationService

pytestmark = pytest.mark.docker


async def _user(session: AsyncSession, code: str, **fields: object) -> User:
    user = User(email=None, referral_code=code, **fields)  # type: ignore[arg-type]
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def test_ban_records_who_did_it(db_session: AsyncSession) -> None:
    """Журнал нужен ровно для спора «за что меня заблокировали»."""
    staff = await _user(db_session, "mod00001", role=UserRole.support)
    target = await _user(db_session, "mod00002")

    changed = await ModerationService(db_session).ban(target.id, actor_id=staff.id)
    await db_session.commit()

    assert changed is True
    await db_session.refresh(target)
    assert target.status is UserStatus.banned
    record = await db_session.scalar(select(AuditLog).where(AuditLog.action == "user.ban"))
    assert record is not None
    assert record.actor_id == staff.id
    assert record.entity_id == str(target.id)


async def test_second_ban_changes_nothing(db_session: AsyncSession) -> None:
    """Повтор не должен плодить записи журнала и подтверждать несделанное."""
    target = await _user(db_session, "mod00003", status=UserStatus.banned)

    assert await ModerationService(db_session).ban(target.id, actor_id=None) is False
    await db_session.commit()

    assert await db_session.scalar(select(AuditLog)) is None


async def test_staff_cannot_be_banned(db_session: AsyncSession) -> None:
    """Одной командой из рабочего чата гасился бы доступ коллеги."""
    colleague = await _user(db_session, "mod00004", role=UserRole.admin)

    with pytest.raises(ServiceError) as refusal:
        await ModerationService(db_session).ban(colleague.id, actor_id=None)

    assert refusal.value.code == "staff_immune"
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

```
uv run pytest backend/core/tests/test_moderation.py -q
```
Ожидание: `ModuleNotFoundError: repibot_core.services.moderation`.

- [ ] **Шаг 3: Реализация**

```python
"""Блокировка аккаунта и заглушение поддержки.

Отдельный сервис, потому что зовут его из разных мест: команда в рабочем
чате сегодня, экран админки завтра. Журнал ведётся здесь же — решение о
блокировке обязано оставлять след независимо от того, кто его принял.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import User, UserRole, UserStatus
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.services.errors import ServiceError

STAFF_ROLES = frozenset({UserRole.support, UserRole.admin})


class ModerationService:
    """Транзакцию закрывает вызывающий."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._audit = AuditRepository(session)

    async def ban(self, user_id: int, *, actor_id: int | None) -> bool:
        user = await self._require(user_id)
        if user.role in STAFF_ROLES:
            # Иначе рабочий чат становится оружием против собственных коллег:
            # прав на это внутри супергруппы никто не разграничивает.
            raise ServiceError("нельзя заблокировать сотрудника", "staff_immune")
        if user.status is UserStatus.banned:
            return False
        user.status = UserStatus.banned
        await self._record("user.ban", user, before="active", after="banned", actor_id=actor_id)
        return True

    async def unban(self, user_id: int, *, actor_id: int | None) -> bool:
        user = await self._require(user_id)
        if user.status is not UserStatus.banned:
            return False
        user.status = UserStatus.active
        await self._record("user.unban", user, before="banned", after="active", actor_id=actor_id)
        return True

    async def mute_support(self, user_id: int, *, actor_id: int | None) -> bool:
        user = await self._require(user_id)
        if user.support_muted_at is not None:
            return False
        user.support_muted_at = datetime.now(UTC)
        await self._record(
            "user.support_mute", user, before="open", after="muted", actor_id=actor_id
        )
        return True

    async def unmute_support(self, user_id: int, *, actor_id: int | None) -> bool:
        user = await self._require(user_id)
        if user.support_muted_at is None:
            return False
        user.support_muted_at = None
        await self._record(
            "user.support_unmute", user, before="muted", after="open", actor_id=actor_id
        )
        return True

    async def _require(self, user_id: int) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise ServiceError("пользователь не найден", "not_found")
        return user

    async def _record(
        self, action: str, user: User, *, before: str, after: str, actor_id: int | None
    ) -> None:
        await self._audit.record(
            action,
            "user",
            actor_id=actor_id,
            entity_id=str(user.id),
            before={"state": before},
            after={"state": after},
        )
```

- [ ] **Шаг 4: Тесты проходят**

```
uv run pytest backend/core/tests/test_moderation.py -q
```

- [ ] **Шаг 5: Дописать остальные случаи**

Разбан снимает статус и пишет `user.unban`; повторный разбан незаблокированного возвращает `False`; заглушение проставляет момент и пишет `user.support_mute`; снятие заглушения обнуляет момент; несуществующий номер даёт `not_found`. Каждый — отдельный тест со строкой документации.

- [ ] **Шаг 6: Итог**

```
uv run pytest backend/core/tests/test_moderation.py -q
uv run ruff format backend/core/src/repibot_core/services/moderation.py backend/core/tests/test_moderation.py
uv run ruff check backend/core/src/repibot_core/services/moderation.py backend/core/tests/test_moderation.py
uv run mypy backend/core/src/repibot_core/services/moderation.py
```

---

### Задача 4: Мгновенная доставка

**Волна 1.**

**Файлы:**
- Изменить: `backend/core/src/repibot_core/tasks.py` (только добавление `wake_outbox`)
- Изменить: `backend/api/src/repibot_api/routers/support.py`, `backend/api/src/repibot_api/routers/admin.py`
- Изменить: `backend/bot/src/repibot_bot/main.py`
- Тест: `backend/api/tests/test_support_routes.py` (дописать), `backend/core/tests/test_outbox_service.py` (дописать)

**Отдаёт:** `repibot_core.tasks.wake_outbox() -> None` — пробуждение очереди, не роняющее вызывающего.

**Запрещено:** трогать `handlers/support.py` (его правит задача 7), `dispatcher.py`, `services/support.py`.

- [ ] **Шаг 1: Тест на безопасность пробуждения**

Очередь уже записана в базу, поэтому недоступный брокер обязан остаться предупреждением в журнале, а не отказом человеку. В `backend/core/tests/test_outbox_service.py`:

```python
async def test_waking_a_dead_broker_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сообщение уже в базе: худшее, чего заслуживает молчащий брокер, — ожидание крона."""

    async def _refuse() -> None:
        msg = "брокер недоступен"
        raise RuntimeError(msg)

    monkeypatch.setattr(tasks.process_outbox, "kiq", _refuse)

    await tasks.wake_outbox()
```

- [ ] **Шаг 2: Убедиться, что тест падает**

```
uv run pytest backend/core/tests/test_outbox_service.py -q -k waking
```
Ожидание: `AttributeError: module 'repibot_core.tasks' has no attribute 'wake_outbox'`.

- [ ] **Шаг 3: Реализация в `tasks.py`**

Рядом с объявлением `process_outbox`:

```python
async def wake_outbox() -> None:
    """Просит разобрать очередь немедленно, не дожидаясь крона.

    Отказ проглатывается намеренно: то, ради чего звали, уже записано в базу
    и уйдёт следующим прогоном крона. Уронить здесь запрос человека значило
    бы поменять минуту ожидания на потерянное действие.
    """
    try:
        await process_outbox.kiq()
    except Exception:  # noqa: BLE001 — природа отказа брокера роли не играет
        logger.warning("не удалось разбудить разбор очереди", exc_info=True)
```

- [ ] **Шаг 4: Пробуждение в маршрутах кабинета**

В `backend/api/src/repibot_api/routers/support.py` после каждого `await session.commit()`, который поставил сообщение в очередь (открытие обращения, ответ человека, закрытие), добавить `await wake_outbox()`. Импорт — `from repibot_core.tasks import wake_outbox`.

- [ ] **Шаг 5: Пробуждение в админке**

То же в `backend/api/src/repibot_api/routers/admin.py` для ответа в обращение и закрытия обращения. Рассылки не трогать: их разбирает своя задача.

- [ ] **Шаг 6: Брокер в процессе бота**

В `backend/bot/src/repibot_bot/main.py` поднять клиентское подключение TaskIQ до опроса обновлений и закрыть после, по образцу приложения API:

```python
    # Бот ставит сообщения в очередь и будит её разбор: без клиентского
    # подключения kiq не с чем говорить, а обращение ждало бы крона.
    await broker.startup()
    try:
        ...
    finally:
        await broker.shutdown()
```

Точное место и имя брокера взять из `backend/core/src/repibot_core/tasks.py` и из того, как это сделано в `backend/api/src/repibot_api/main.py`.

- [ ] **Шаг 7: Проверка**

```
uv run pytest backend/core/tests/test_outbox_service.py backend/api/tests/test_support_routes.py backend/bot/tests -q
uv run ruff format <свои файлы>
uv run mypy backend/core/src/repibot_core/tasks.py backend/api/src/repibot_api/routers backend/bot/src
```

---

### Задача 5: Сервис поддержки — закрытие, заглушение, синхронизация имени

**Волна 2. Единственная задача, правящая `services/support.py`.**

**Файлы:**
- Изменить: `backend/core/src/repibot_core/services/support.py`
- Тест: `backend/core/tests/test_tickets.py` (дописать)

**Потребляет:** `topic_name`, `TOPIC_MARKS` (задача 1), вид `ticket_closed` (задача 1), `User.support_muted_at` (задача 1).

**Отдаёт:**
- `SupportService.close(ticket_id, *, by_staff: bool, notify: bool) -> None`
- код отказа `support_muted` из `open` и `reply_from_user`
- сообщение очереди вида `{"ticket_id": int, "sync": True}` — просьба привести имя темы в соответствие

**Запрещено:** трогать `dispatcher.py` и `support_chat.py` (задача 6), `moderation.py`. В `routers/support.py`, `routers/admin.py` и `handlers/support.py` разрешена **единственная** правка — привести вызовы `close` к новой подписи; всё остальное в этих файлах принадлежит задачам 4 и 7.

- [ ] **Шаг 1: Тест на запрет заглушённому**

В `backend/core/tests/test_tickets.py`:

```python
async def test_muted_person_cannot_open_a_ticket(db_session: AsyncSession) -> None:
    """Заглушение закрывает разговор, а не подписку: отказ приходит здесь."""
    user = await _user(db_session, 300_100, "ticket90")
    user.support_muted_at = datetime.now(UTC)
    await db_session.commit()

    with pytest.raises(ServiceError) as refusal:
        await _service(db_session).open(user.id, "впустите")

    assert refusal.value.code == "support_muted"
```

И такой же на `reply_from_user` в уже открытом обращении.

- [ ] **Шаг 2: Убедиться, что тесты падают**

```
uv run pytest backend/core/tests/test_tickets.py -q -k muted
```
Ожидание: обращение создаётся, `ServiceError` не поднимается.

- [ ] **Шаг 3: Реализация запрета**

В `SupportService` добавить:

```python
    async def _require_speech(self, user_id: int) -> None:
        """Заглушённому закрыт разговор, но не подписка и не оплата."""
        muted = await self._session.scalar(
            select(User.support_muted_at).where(User.id == user_id)
        )
        if muted is not None:
            raise ServiceError("доступ к поддержке ограничен", "support_muted")
```

Звать первым делом в `open` и в `reply_from_user` — до проверки предела открытых обращений: заглушённому незачем узнавать, сколько у него обращений.

- [ ] **Шаг 4: Тест на уведомление о закрытии**

```python
async def test_staff_closing_tells_the_person(db_session: AsyncSession) -> None:
    """Иначе человек узнаёт о закрытии, только заглянув в кабинет."""
    user = await _user(db_session, 300_101, "ticket91")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    await db_session.commit()

    await service.close(ticket.id, by_staff=True, notify=True)
    await db_session.commit()

    kinds = list(await db_session.scalars(select(NotificationDelivery.kind)))
    assert "ticket_closed" in kinds


async def test_silent_closing_stays_silent(db_session: AsyncSession) -> None:
    """Тихое закрытие для случая, когда разговор кончился ничем."""
    user = await _user(db_session, 300_102, "ticket92")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    await db_session.commit()

    await service.close(ticket.id, by_staff=True, notify=False)
    await db_session.commit()

    kinds = list(await db_session.scalars(select(NotificationDelivery.kind)))
    assert "ticket_closed" not in kinds
```

- [ ] **Шаг 5: Реализация закрытия**

Подпись `close` становится `async def close(self, ticket_id: int, *, by_staff: bool, notify: bool) -> None`. Параметр обязателен и без значения по умолчанию: тихое закрытие — это решение, а не забытый аргумент. После записи системной отметки:

```python
        if notify:
            await NotificationService(self._session).enqueue(
                user_id=ticket.user_id,
                kind="ticket_closed",
                dedup_key=f"ticket:{ticket.id}:closed",
                params={"id": ticket.id},
            )
```

Поправить существующих вызывающих — **только сам вызов, ничего вокруг**: `routers/support.py` (кабинет, `notify=False`), `routers/admin.py` (`notify=True`), `handlers/support.py` (`notify=True`).

- [ ] **Шаг 6: Тест на просьбу переименовать**

```python
async def test_staff_reply_asks_to_repaint_the_topic(db_session: AsyncSession) -> None:
    """Ответ из темы меняет состояние, но в Telegram ничего не отправляет:
    без этой просьбы название осталось бы красным на решённом обращении."""
    user = await _user(db_session, 300_103, "ticket93")
    service = _service(db_session)
    ticket = await service.open(user.id, "вопрос")
    ticket.telegram_topic_id = 4242
    await db_session.commit()

    await service.reply_from_staff(4242, "ответ", telegram_id=999, message_id=1)
    await db_session.commit()

    payloads = list(await db_session.scalars(select(OutboxMessage.payload)))
    assert {"ticket_id": ticket.id, "sync": True} in payloads
```

- [ ] **Шаг 7: Реализация просьбы**

В `reply_from_staff`, после успешного `_staff_reply`:

```python
        # Ответ уже лежит в теме — отправлять туда нечего. Но состояние
        # обращения сменилось, и название темы обязано это показать.
        await self._outbox.add(TOPIC_SUPPORT_OUTBOUND, {"ticket_id": ticket.id, "sync": True})
```

- [ ] **Шаг 8: Итог**

```
uv run pytest backend/core/tests/test_tickets.py -q
uv run ruff format backend/core/src/repibot_core/services/support.py backend/core/tests/test_tickets.py
uv run mypy backend/core/src/repibot_core/services/support.py
```

---

### Задача 6: Тема супергруппы — переименование, карточка, порядок

**Волна 2.**

**Файлы:**
- Изменить: `backend/core/src/repibot_core/integrations/telegram/support_chat.py`
- Изменить: `backend/core/src/repibot_core/services/dispatcher.py`
- Изменить: `backend/core/src/repibot_core/tasks.py` (только передача фасада устройств в `_dispatcher`)
- Тест: `backend/core/tests/test_support_chat.py` (дописать)

**Потребляет:** `topic_name` (задача 1), `build_card`, `devices_for_card` (задача 2).

**Отдаёт:** `SupportChat.rename_topic(topic_id: int, name: str) -> None`; порядок разбора темы из спецификации.

**Запрещено:** трогать `services/support.py` (задача 5) и хендлеры бота (задача 7). В `tasks.py` менять только строку сборки диспетчера — `wake_outbox` там уже есть от задачи 4.

- [ ] **Шаг 1: Тест на порядок вызовов**

Двойник супергруппы в `test_support_chat.py` уже устроен через `httpx.MockTransport`, и порядок вызовов читается из путей запросов — тем же приёмом пользуется существующий `test_topic_id_is_stored_before_the_message_is_sent`. Дописать в тот же файл:

```python
@pytest.mark.docker
async def test_topic_is_repainted_before_it_is_closed(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Закрытую тему Bot API переименовывать отказывается.

    Обратный порядок оставил бы решённое обращение красным навсегда — а по
    цвету персонал и разбирает, что ещё ждёт ответа.
    """
    user = User(email=None, telegram_id=310_010, referral_code="topic010")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    service = SupportService(db_session, _settings())
    ticket = await service.open(user.id, "не открывается")
    await db_session.commit()
    factory = create_session_factory(engine)
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", maxsplit=1)[-1]
        calls.append(method)
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_thread_id": 21, "message_id": 5}},
        )

    chat = _chat(handler)
    try:
        await _dispatcher(factory, chat).process(db_session)
        # Просьба закрыть кладётся в очередь напрямую, а не через `close`:
        # подпись того метода в этой же волне меняет соседняя задача, и тест
        # не должен её ждать.
        ticket.status = TicketStatus.closed
        await OutboxRepository(db_session).add(
            TOPIC_SUPPORT_OUTBOUND, {"ticket_id": ticket.id, "body": "", "close": True}
        )
        await db_session.commit()
        await _dispatcher(factory, chat).process(
            db_session, now=datetime.now(UTC) + timedelta(minutes=1)
        )
    finally:
        await chat.aclose()

    assert calls.index("editForumTopic") < calls.index("closeForumTopic")
```

- [ ] **Шаг 2: Тест на карточку один раз**

```python
@pytest.mark.docker
async def test_card_opens_the_topic_and_is_not_repeated(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Карточка открывает тему; на второй реплике сотрудник её уже видел."""
    user = User(
        email="card@example.com",
        telegram_id=310_011,
        telegram_username="cardholder",
        referral_code="topic011",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    service = SupportService(db_session, _settings())
    ticket = await service.open(user.id, "не открывается")
    await db_session.commit()
    factory = create_session_factory(engine)
    texts: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", maxsplit=1)[-1]
        if method == "sendMessage":
            texts.append(str(json.loads(request.content)["text"]))
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_thread_id": 22, "message_id": 5}},
        )

    chat = _chat(handler)
    try:
        await _dispatcher(factory, chat).process(db_session)
        await service.reply_from_user(user.id, ticket.id, "и ещё вот что")
        await db_session.commit()
        await _dispatcher(factory, chat).process(
            db_session, now=datetime.now(UTC) + timedelta(minutes=1)
        )
    finally:
        await chat.aclose()

    assert len([text for text in texts if "@cardholder" in text]) == 1
    assert texts[0].startswith("👤")
```

- [ ] **Шаг 3: Тест на молчание при неизменном состоянии**

```python
@pytest.mark.docker
async def test_unchanged_status_costs_no_extra_call(
    db_session: AsyncSession, engine: AsyncEngine
) -> None:
    """Вторая реплика человека состояния не меняет: тема уже красная.

    Переименование на каждом сообщении — вызов Bot API на каждое сообщение,
    а разбор берёт до сотни сообщений за раз.
    """
```
Собрать по образцу шага 2: первый разбор, затем ответ человека и второй разбор; убедиться, что `editForumTopic` в списке вызовов не появился ни разу.

- [ ] **Шаг 4: Поправить существующий тест повтора**

`test_topic_id_is_stored_before_the_message_is_sent` ждёт `calls[2:] == ["sendMessage"]`. С карточкой первый прогон падает на ней, отметка не проставляется, и повтор шлёт карточку заново — теперь ожидание `["sendMessage", "sendMessage"]`. Это то самое задвоение, которое спецификация признаёт осознанным: вторая карточка в теме безобидна, потерянная — нет. Отразить это в строке документации теста, а не молча поменять число.

- [ ] **Шаг 5: Убедиться, что тесты падают**

```
uv run pytest backend/core/tests/test_support_chat.py -q
```
Ожидание: `AttributeError: 'SupportChat' object has no attribute 'rename_topic'` и расхождение порядка вызовов.

- [ ] **Шаг 6: Переименование темы**

В `support_chat.py`:

```python
    async def rename_topic(self, topic_id: int, name: str) -> None:
        """Меняет имя темы. Закрытую тему Bot API переименовывать отказывается,
        поэтому вызывать это нужно до закрытия."""
        await self._call(
            "editForumTopic",
            {"chat_id": self._chat_id(), "message_thread_id": topic_id, "name": name},
        )
```

- [ ] **Шаг 7: Новый порядок в диспетчере**

`handle_support_outbound` переписывается по спецификации:

```python
    async def handle_support_outbound(payload: dict[str, object]) -> None:
        """Доводит сообщение до темы и держит её название в согласии с состоянием.

        Имя правится до закрытия: закрытую тему Bot API переименовывать
        отказывается, и решённое обращение осталось бы красным.
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
                ticket.telegram_topic_id = await support.create_topic(topic_name(ticket))
                # Своя фиксация: падение на отправке не должно приводить ко
                # второй теме при повторе — переписка разорвалась бы надвое.
                await session.commit()
            topic_id = ticket.telegram_topic_id

            if ticket.topic_status_mark is None:
                counts = (
                    await devices_for_card(session, panel_devices, ticket.user_id)
                    if panel_devices is not None
                    else None
                )
                await support.post(topic_id, await build_card(session, ticket, devices=counts))
                # Отметка ставится вместе с карточкой, а не отдельным шагом:
                # имя новой темы уже собрано с правильной меткой, и без этого
                # проверка ниже переименовала бы её в то же самое.
                ticket.topic_status_mark = ticket.status
                await session.commit()

            body = str(payload.get("body") or "")
            if body:
                await support.post(topic_id, body)

            if ticket.topic_status_mark is not ticket.status:
                await support.rename_topic(topic_id, topic_name(ticket))
                ticket.topic_status_mark = ticket.status
                await session.commit()

            closing = bool(payload.get("close"))
        if closing:
            await support.close_topic(topic_id)
```

`build_dispatcher` получает новый необязательный параметр `panel_devices: PanelDevices | None = None`.

- [ ] **Шаг 8: Передача фасада в задаче**

В `tasks.py`, в `_dispatcher`, единственная правка:

```python
    from repibot_core.integrations.remnawave.devices import PanelDevices
    ...
    return build_dispatcher(
        factory,
        users=PanelUsers(panel),
        telegram=telegram,
        support=support,
        panel_devices=PanelDevices(panel),
    )
```

- [ ] **Шаг 9: Тесты проходят**

```
uv run pytest backend/core/tests/test_support_chat.py backend/core/tests/test_tickets.py -q
uv run ruff format <свои файлы>
uv run mypy backend/core/src/repibot_core
```

---

### Задача 7: Семь команд в теме и обрыв на заблокированном

**Волна 3.**

**Файлы:**
- Изменить: `backend/bot/src/repibot_bot/handlers/support.py`
- Изменить: `backend/bot/src/repibot_bot/middleware.py`
- Тест: `backend/bot/tests/test_support_handlers.py`, `backend/bot/tests/test_user_middleware.py`

**Потребляет:** `ModerationService` (задача 3), `close(..., notify=)` (задача 5), `build_card`, `devices_for_card` (задача 2), `wake_outbox` (задача 4).

**Запрещено:** трогать что-либо в `backend/core` и `backend/api`.

- [ ] **Шаг 1: Тест на обрыв заблокированного в боте**

В `backend/bot/tests/test_user_middleware.py`:

```python
async def test_blocked_account_stops_at_the_door(...) -> None:
    """Бан без этого фикция: человек продолжает покупать подписку через бота."""
```
Проверяется, что обработчик не вызван и что человеку ответили один раз.

- [ ] **Шаг 2: Тесты на команды**

В `backend/bot/tests/test_support_handlers.py` — по тесту на каждую команду:

- `/info` присылает карточку и не заводит реплику в переписке;
- `/close` закрывает и ставит уведомление, `/close_silent` — закрывает без него;
- `/mute` проставляет момент, `/unmute` снимает;
- `/ban` блокирует и тихо закрывает обращение;
- `/ban` на сотруднике отвечает отказом и никого не блокирует;
- `/unban` снимает блокировку;
- повтор любой команды отвечает «уже», а не ложным подтверждением;
- текст команды не уходит человеку как ответ поддержки.

- [ ] **Шаг 3: Убедиться, что тесты падают**

```
uv run pytest backend/bot/tests -q
```

- [ ] **Шаг 4: Обрыв в middleware**

После получения `user`, до сборки остальных зависимостей:

```python
            if user.status is not UserStatus.active:
                # Заблокированный не должен ни покупать, ни писать: без этой
                # проверки бан отражается только на входе в кабинет.
                if isinstance(event, Message):
                    await event.answer(translate(user.language, "bot.blocked"))
                return None
```

Там же собрать фасад устройств один раз на процесс, рядом с `BotApi`, и класть в `data["panel_devices"]`: команда `/info` иначе открывала бы новый пул соединений на каждый вызов.

- [ ] **Шаг 5: Команды**

Каждая команда — своя функция с строкой документации. Общая часть — поиск обращения по теме — выносится в помощник `_ticket_of_topic(session, message)`, возвращающий `Ticket | None`; посторонняя тема молча игнорируется, как сейчас.

Ответы в тему — русские строки прямо в коде:

```python
CONFIRM_CLOSED = "Обращение №{id} закрыто, человек уведомлён."
CONFIRM_CLOSED_SILENT = "Обращение №{id} закрыто без уведомления."
CONFIRM_MUTED = "Поддержка для этого человека закрыта."
CONFIRM_UNMUTED = "Поддержка снова открыта."
CONFIRM_BANNED = "Аккаунт заблокирован, обращение №{id} закрыто."
CONFIRM_UNBANNED = "Блокировка снята."
ALREADY_CLOSED = "Обращение уже закрыто."
ALREADY_MUTED = "Поддержка для этого человека уже закрыта."
ALREADY_OPEN = "Поддержка и так открыта."
ALREADY_BANNED = "Аккаунт уже заблокирован."
NOT_BANNED = "Аккаунт не заблокирован."
STAFF_IMMUNE = "Это сотрудник — заблокировать нельзя."
```

`/ban` закрывает обращение тихо: отвечать заблокированному некому.

- [ ] **Шаг 6: Регистрация**

Все семь команд регистрируются **до** `handle_topic_message`, иначе их текст уйдёт человеку как ответ поддержки. Существующая регистрация `/close` — образец:

```python
    router.message.register(handle_topic_info, in_support_chat, Command("info"))
    router.message.register(handle_topic_close, in_support_chat, Command("close"))
    router.message.register(handle_topic_close_silent, in_support_chat, Command("close_silent"))
    router.message.register(handle_topic_mute, in_support_chat, Command("mute"))
    router.message.register(handle_topic_unmute, in_support_chat, Command("unmute"))
    router.message.register(handle_topic_ban, in_support_chat, Command("ban"))
    router.message.register(handle_topic_unban, in_support_chat, Command("unban"))
    router.message.register(handle_topic_message, in_support_chat, F.message_thread_id)
```

- [ ] **Шаг 7: Пробуждение очереди**

После `await session.commit()` в обработчиках, поставивших сообщение в очередь (обращение из лички, ответ человека, закрытие), добавить `await wake_outbox()`.

- [ ] **Шаг 8: Итог**

```
uv run pytest backend/bot/tests -q
uv run ruff format backend/bot/src backend/bot/tests
uv run mypy backend/bot/src
```

---

### Задача 8: Документация

**Волна 3.**

**Файлы:**
- Изменить: `docs/deployment.md`

**Запрещено:** трогать код.

- [ ] **Шаг 1: Права бота**

В разделе «10. Поддержка, напоминания и рассылки», где описана настройка супергруппы, дописать: боту нужно право управления темами (`can_manage_topics`), иначе он не сможет переименовывать темы под состояние обращения, и все они останутся с меткой, которая стояла при создании.

- [ ] **Шаг 2: Таблица команд**

Добавить таблицу из семи команд с колонками «команда», «что делает», «что видит человек». Отдельной строкой отметить, что `/close` уведомляет человека, а `/close_silent`, `/ban` и закрытие из кабинета — нет.

- [ ] **Шаг 3: Метки**

Объяснить метки 🔴 🟡 ✅ и то, что у обращений, созданных до обновления, метка появится при первом же движении, а карточка придёт вдогонку.

- [ ] **Шаг 4: Диагностика**

В таблицу диагностики дописать строку: тема не переименовывается — проверить право `can_manage_topics`; карточка без устройств — панель не ответила, смотреть журнал разбора очереди.

- [ ] **Шаг 5: Проверка**

```
uv run pytest tools/tests/test_docs.py -q
```

---

## Проверка после всех волн

Ведущий прогоняет целиком, тремя частями, чтобы уложиться в предел времени:

```
uv run pytest backend/core/tests -q
uv run pytest backend/api/tests backend/bot/tests backend/worker/tests tools/tests -q
uv run check
```
