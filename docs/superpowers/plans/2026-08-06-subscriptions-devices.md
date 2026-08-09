# Подписки, этап 2b — план реализации

> **Для агентов:** ОБЯЗАТЕЛЬНЫЙ ПОДСКИЛЛ: используйте superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для выполнения плана задача за задачей. Шаги размечены чекбоксами (`- [ ]`).

**Цель:** довести подпроект 2 до конца — устройства и трафик в кабинете, приём событий панели, сверка по расписанию и интерфейсы веба и MiniApp поверх готового API.

**Архитектура:** трафик и устройства не дублируются у нас — читаются из панели по требованию и кэшируются в Valkey на минуту. Вебхуки панели дают повод посмотреть, но никогда не двигают дату окончания. Сверка по расписанию зовёт то же самое примирение, что и выдача доступа, и записывает найденные расхождения вместо молчаливого исправления.

**Стек:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, httpx, TaskIQ, Valkey, Postgres 18; React 19, Next.js 16, TanStack Query v5, TanStack Router, Vitest, Playwright.

**Спецификация:** [docs/superpowers/specs/2026-08-06-subscriptions-design.md](../specs/2026-08-06-subscriptions-design.md)

**Предшествующий этап:** [2a — панель и подписка](./2026-08-06-subscriptions-core.md), выполнен полностью и подтверждён на живой панели 3.2.1.

## Состояние выполнения

Автоматизированная часть этапа выполнена полностью, задачи 1–16. Проверка
задачи 16 прошла через отдельный compose-проект `repibot-e2e`: настоящий
браузер работает через Nginx, FastAPI, Postgres, Valkey и worker, а HTTP-обёртка
над `FakePanel` предоставляет устройства и трафик по тем же контрактам, что
клиент Remnawave. Итоговый Playwright-прогон — 11/11 сценариев; `uv run check`
2026-08-09 прошёл все восемь стадий, включая 547 Python-тестов и 213
frontend-тестов. Остались девять известных предупреждений сериализатора
Pydantic в тестах заглушки панели.

**Проверка против живой Remnawave 3.2.1 пока не выполнена.** В локальном `.env`
параметры панели заданы, но нет обозначенного тестового пользователя и клиента,
а публикация вебхука на указанном внешнем адресе не подтверждена. Выполнять
revoke, отвязку и смену лимита над неизвестной учётной записью небезопасно.
Перед выпуском остаётся вручную пройти шаг 5 задачи 16: проверить
подпись и фактическое имя заголовка, восстановление после revoke, данные
реального клиента, отвязку устройства, согласованность трафика и запись
расхождения после ручной смены лимита. Заглушка подтверждает форму запросов и
ответов, но не заменяет эту проверку поведения живой панели.

| Волна | Задачи | Состояние |
|---|---|---|
| 1 | 1 модели панели, 2 таблицы событий и расхождений | готово |
| 2 | 3 фасады устройств и трафика, 4 репозитории | готово |
| — | общий кэш панели перед волной 3 | готово |
| 3 | 5 устройства, 6 трафик, 7 вебхуки | готово |
| 4 | 8 клиентское API, 9 endpoint вебхука, 10 сверка | готово |
| 5 | 11 типы, хуки и словари фронтенда | готово |
| 6 | 12 витрина, 13 веб-кабинет, 14 MiniApp | готово |
| 7 | 15 HTTP-заглушка и посев E2E | готово |
| 8 | 16 Playwright и документация | автоматизировано; живая панель ожидает проверки |

### Что нашлось при сборке

- Идентификатор пользователя панели в API 3.2.1 имеет тип `number` и может
  прийти как `42.0`; на границах он приводится к целому, а фронтенд не теряет
  типобезопасность.
- Лимит попыток API нужно считать до создания клиента панели: иначе запросы
  устройств и трафика принимались без ограничителя.
- Webhook подписывается по сырым байтам тела. Повторная доставка возвращает
  успех, событие хранится идемпотентно, а секрет не попадает в URL.
- Плановая сверка не маскирует ручное расхождение: сначала успешно завершает
  reconcile во внешней панели, затем записывает finding. Это не атомарная
  транзакция между панелью и БД: сбой после исправления панели может оставить
  finding не записанным.
- `pending_provision` и отсутствие подписки не должны запускать запросы
  устройств и трафика: иначе ожидаемое состояние сопровождалось ложными
  красными ошибками панели.
- Публичный ответ подписки не содержит достоверного снимка цены, описания и
  длительности покупки. Поэтому кабинет использует специализированную карточку
  текущей подписки, а не подставляет изменяемые данные текущего тарифа.
- Генерация QR-кода асинхронна и может завершиться ошибкой; кабинет показывает
  восстановимый fallback со ссылкой вместо вечного состояния загрузки.
- Настройки языка и темы браузера нужно читать после монтирования без изменения
  серверной разметки, чтобы Next.js не получал hydration mismatch.
- MiniApp дожидается завершения Telegram-входа до запросов защищённых маршрутов;
  иначе быстрый экран успевал получить 401 до появления access token.
- HTTP-посев должен менять сохранённый объект `FakePanel`, а не копию ответа;
  иначе суммарный трафик исчезал при следующем GET. Порт посева опубликован
  только на `127.0.0.1`, а SQL пользователя и подписки выполняется атомарно.
- Сквозной сценарий сверяет точное подтверждение отвязки и итоговый пустой
  список. Русский форматтер единиц использует `КБ/ГБ`, что закреплено в
  браузерном ожидании.
- Весь E2E-стек разделяет один адрес Nginx, базу и Valkey. После добавления
  ещё двух регистраций параллельный запуск исчерпывал продуктовый лимит в пять
  попыток; Playwright теперь использует один worker, а перед группой сценариев
  подписки очищается только её регистрационный ключ в изолированном Valkey.

## Волны выполнения

Внутри волны задачи идут параллельными исполнителями, между волнами — полный прогон `uv run check` и коммиты.

| Волна | Задачи | Почему вместе |
|---|---|---|
| 1 | 1 модели панели, 2 таблицы событий и расхождений | Ни одного общего файла |
| 2 | 3 фасады устройств и трафика, 4 репозитории | 3 после 1, 4 после 2 |
| — | `services/panel_cache.py` пишет ведущий до волны 3 | Общий файл двух задач |
| 3 | 5 сервис устройств, 6 сервис трафика, 7 сервис вебхуков | 5 и 6 после 3, 7 после 4 |
| 4 | 8 клиентское API, 9 приёмник вебхуков, 10 реконсиляция | 8 после 5 и 6, 9 после 7, 10 после 4 |
| 5 | 11 типы, хуки и словари фронтенда | После всех эндпоинтов |
| 6 | 12 витрина в вебе, 13 кабинет, 14 MiniApp | Все после 11, приложения разные |
| 7 | 15 панель-заглушка и посев для сквозных тестов | Готовит стек для 16 |
| 8 | 16 сквозной сценарий и документация | Последняя |

## Глобальные ограничения

- Ветка работы — `dev`. Отдельные ветки, если понадобятся, создаются от `dev`.
- Каждая задача заканчивается прогоном `uv run check` без ошибок и одним коммитом. Сообщение коммита на русском в формате `тип: краткое описание`.
- Тест пишется первым и падает до реализации.
- Бизнес-логика — только в `backend/core/src/repibot_core/services` и `.../domain`. В роутерах FastAPI и хендлерах aiogram её нет. Исключение уже принято в этапе 2a и сохраняется: ограничение частоты запросов живёт в роутере, как в `routers/auth.py`.
- Комментарии, докстринги и сообщения — на русском. Комментарий объясняет причину решения, а не пересказывает код.
- `mypy` в strict и `ruff` с набором из `pyproject.toml` — блокирующие. Аннотации обязательны везде, включая тесты.
- Новая переменная окружения добавляется одновременно в `Settings`, `.env.example` и `docs/deployment.md`. **Все переменные этапа заведены ещё в 2a** — новых не нужно.
- Тексты ошибок API не локализуются: ответ несёт код, фразу подбирает фронтенд. Новые коды этапа: `panel_unavailable` (уже есть), `device_not_found`, `subscription_missing` (уже есть), `webhooks_disabled`.
- Цвета, отступы и типографика — из `docs/design/repibot-brandbook.md` через токены `packages/ui`. Свои цвета и размеры в приложениях не появляются.
- Тесты, которым нужен Postgres, помечаются `pytestmark = pytest.mark.docker`.
- `backend/core/src/repibot_core/integrations/remnawave/models.py` — генерируемый файл. Правится только через `tools/gen_remnawave_models.py` с последующей перегенерацией.
- **Веб-приложение на Next.js 16.** В `frontend/apps/web/AGENTS.md` записано требование: перед написанием кода читать руководство в `node_modules/next/dist/docs/`, потому что API этой версии отличается от привычного. Это обязательно для задач 12 и 13.
- Зависимость `qrcode@^1.5` в `frontend/apps/web` ставит **ведущий** перед волной 6. Исполнителям задач ставить или обновлять пакеты не нужно: `pnpm-lock.yaml` общий, и параллельные исполнители за него дерутся.

## Проверенные факты о панели 3.2.1

Получены из схемы `docs/remnawave-api/api-1.json` и пробным прогоном генератора 2026-08-06.

| Что | Значение |
|---|---|
| Устройства пользователя | `GET /api/hwid/devices/{userId}`, `userId` — число в пути |
| Удаление устройства | `POST /api/hwid/devices/delete`, тело `{"userId": number, "hwid": string}` |
| Ответ по устройствам | `response.total` и `response.devices[]` с `hwid`, `userId`, `platform`, `osVersion`, `deviceModel`, `userAgent`, `requestIp`, `createdAt`, `updatedAt` — все, кроме `hwid`, `userId` и дат, допускают `null` |
| Трафик по дням | `GET /api/bandwidth-stats/users/{userId}?start=YYYY-MM-DD&end=YYYY-MM-DD`, обе даты обязательны |
| Ответ по трафику | `response.categories[]` — даты, `response.series[]` с `name`, `total`, `data[]` по тем же категориям, `response.topNodes[]`, `response.sparklineData[]` |
| Текущее потребление | Приходит прямо в объекте пользователя: `userTraffic.usedTrafficBytes` и `lifetimeUsedTrafficBytes` |
| События вебхука | `user.created/modified/deleted/revoked/disabled/enabled/limited/expired/traffic_reset/first_connected/bandwidth_usage_threshold_reached/not_connected/expiration`, `user_hwid_devices.added/deleted` |
| Тело события | `{"scope", "event", "timestamp", "data"}`; у событий пользователя `data` — сам пользователь, у событий устройств `data.user` и `data.device` |
| Подписи в схеме нет | Вебхуки исходящие; имя заголовка берётся из `REMNAWAVE_WEBHOOK_HEADER` |

**Перенумерация сгенерированных классов.** После добавления трёх новых корневых схем генератор выдаёт классы в таком порядке: `Status`, `TrafficLimitStrategy`, `CreateUserBodyDto`, `DeleteUserHwidDeviceBodyDto`, `Info`, `Inbound`, `InternalSquad`, `Response`, `GetInternalSquadsResponseDto`, `TopNode`, `Series`, `Response1`, `GetStatsUserUsageResponseDto`, `Device`, `Response2`, `GetUserHwidDevicesResponseDto`, `ResolveUserBodyDto`, `Status1`, `UpdateUserBodyDto`, `Status2`, `ActiveInternalSquad`, `UserTraffic`, `Response3`, `UserResponseDto`.

То есть **`PanelUser` съезжает с `Response1` на `Response3`**. Ради этого и написан `types.py`: правится один файл, а не весь код. Тест `test_remnawave_types.py` ловит промах.

---

### Задача 1: Модели устройств и трафика

**Файлы:**
- Изменить: `tools/gen_remnawave_models.py`
- Изменить (перегенерацией): `backend/core/src/repibot_core/integrations/remnawave/models.py`
- Изменить: `backend/core/src/repibot_core/integrations/remnawave/types.py`
- Изменить: `backend/core/tests/test_remnawave_types.py`

**Интерфейсы:**
- Отдаёт: `PanelDevice`, `PanelUsage`, `DeleteDeviceBody` из `repibot_core.integrations.remnawave.types`; псевдоним `PanelUser` переезжает на новый класс.

- [ ] **Шаг 1: Дописать падающий тест**

В `backend/core/tests/test_remnawave_types.py` добавить:

```python
def test_panel_device_has_hwid_and_platform() -> None:
    """Псевдоним устройства должен пережить перенумерацию классов."""
    assert {"hwid", "userId", "platform", "deviceModel", "createdAt"} <= set(
        PanelDevice.model_fields
    )


def test_panel_usage_has_categories_and_series() -> None:
    assert {"categories", "series"} <= set(PanelUsage.model_fields)
```

Импорт в шапке файла дополнить: `PanelDevice`, `PanelUsage`.

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_remnawave_types.py -q`
Ожидание: FAIL, `ImportError: cannot import name 'PanelDevice'`

- [ ] **Шаг 3: Расширить генератор**

В `tools/gen_remnawave_models.py` привести `ROOT_SCHEMAS` к виду:

```python
ROOT_SCHEMAS: tuple[str, ...] = (
    "CreateUserBodyDto",
    "DeleteUserHwidDeviceBodyDto",
    "GetInternalSquadsResponseDto",
    "GetStatsUserUsageResponseDto",
    "GetUserHwidDevicesResponseDto",
    "ResolveUserBodyDto",
    "UpdateUserBodyDto",
    "UserResponseDto",
)
```

- [ ] **Шаг 4: Перегенерировать модели**

Запуск: `uv run python tools/gen_remnawave_models.py`
Ожидание: «Сгенерировано схем: 8», файл около 271 строки.

- [ ] **Шаг 5: Поправить псевдонимы**

В `types.py` заменить и дополнить:

```python
# Номер меняется от состава корневых схем: добавление устройств и трафика
# сдвинуло пользователя с Response1 на Response3. Ради этого файл и написан —
# правится одна строка вместо всего кода.
PanelUser = models.Response3
PanelDevice = models.Device
PanelUsage = models.Response1

DeleteDeviceBody = models.DeleteUserHwidDeviceBodyDto
```

`DeleteDeviceBody` и оба новых типа добавить в `__all__`, список держать отсортированным.

- [ ] **Шаг 6: Запустить тесты**

Запуск: `uv run pytest backend/core/tests/test_remnawave_types.py backend/core/tests/test_remnawave_facades.py -q && uv run verify-generated`
Ожидание: PASS и «Сгенерированные файлы актуальны».

- [ ] **Шаг 7: Коммит**

```bash
git add tools/gen_remnawave_models.py backend/core/src/repibot_core/integrations/remnawave backend/core/tests/test_remnawave_types.py
git commit -m "feat: модели устройств и трафика панели"
```

---

### Задача 2: Таблицы событий и расхождений

**Файлы:**
- Создать: `backend/core/src/repibot_core/db/models/webhook.py`
- Создать: `backend/core/src/repibot_core/db/models/reconciliation.py`
- Изменить: `backend/core/src/repibot_core/db/models/__init__.py`
- Создать: `backend/core/src/repibot_core/db/migrations/versions/0005_webhooks.py`
- Тест: `backend/core/tests/test_webhook_models.py`

**Интерфейсы:**
- Отдаёт: `WebhookEvent`, `WebhookSource`, `ReconciliationFinding`, `FindingAction` из `repibot_core.db.models`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_webhook_models.py
"""Схема журналов вебхуков и расхождений."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction, ReconciliationFinding, WebhookEvent, WebhookSource

pytestmark = pytest.mark.docker


async def test_same_event_cannot_be_stored_twice(db_session: AsyncSession) -> None:
    """Повторная доставка не должна обрабатываться дважды."""
    for _ in range(2):
        db_session.add(
            WebhookEvent(
                source=WebhookSource.remnawave,
                event_id="user.expired:2026-08-06T12:00:00Z:42",
                event="user.expired",
                payload={"scope": "user"},
                received_at=datetime.now(UTC),
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_same_event_id_from_other_source_is_allowed(db_session: AsyncSession) -> None:
    """Идентификаторы источников независимы: совпадение строк — совпадение, а не дубль."""
    for source in (WebhookSource.remnawave, WebhookSource.yookassa):
        db_session.add(
            WebhookEvent(
                source=source,
                event_id="одинаковая-строка",
                event="что-то",
                payload={},
                received_at=datetime.now(UTC),
            )
        )
    await db_session.flush()


async def test_finding_records_both_sides(db_session: AsyncSession) -> None:
    """Расхождение бесполезно без обеих сторон: непонятно, что с чем разошлось."""
    finding = ReconciliationFinding(
        run_id="0f6a1c2e-0000-4000-8000-000000000001",
        user_id=None,
        field="expireAt",
        ours="2026-09-06T12:00:00+00:00",
        theirs="2026-10-06T12:00:00+00:00",
        action=FindingAction.fixed,
        created_at=datetime.now(UTC),
    )
    db_session.add(finding)
    await db_session.flush()
    assert finding.id > 0
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_webhook_models.py -q`
Ожидание: FAIL, `ImportError: cannot import name 'WebhookEvent'`

- [ ] **Шаг 3: Написать модель событий**

```python
# backend/core/src/repibot_core/db/models/webhook.py
"""Входящие вебхуки: приняли, сохранили, обработали ровно один раз."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class WebhookSource(StrEnum):
    remnawave = "remnawave"
    yookassa = "yookassa"


class WebhookEvent(Base):
    """Журнал принятых событий.

    Тело сохраняется целиком: разбор спорного случая через неделю невозможен,
    если у нас осталась только наша интерпретация чужого сообщения.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("source", "event_id", name="uq_webhook_events_source_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[WebhookSource] = mapped_column(
        Enum(WebhookSource, name="webhook_source", native_enum=True)
    )
    # Панель своего идентификатора события не присылает, поэтому он собирается
    # из события, отметки времени и идентификатора пользователя.
    event_id: Mapped[str] = mapped_column(String(255))
    event: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Шаг 4: Написать модель расхождений**

```python
# backend/core/src/repibot_core/db/models/reconciliation.py
"""Расхождения между нашей БД и панелью."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811 — не путать с uuid.UUID
from sqlalchemy.orm import Mapped, mapped_column

from repibot_core.db.base import Base


class FindingAction(StrEnum):
    fixed = "fixed"
    skipped = "skipped"


class ReconciliationFinding(Base):
    """Что разошлось, каким было у нас и в панели, что с этим сделали.

    Расхождение почти всегда означает ручную правку админа в панели, и о ней
    надо знать. Поэтому запись делается всегда, а не только при отказе.
    """

    __tablename__ = "reconciliation_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Идентификатор прогона: без него отчёт превращается в ленту без границ,
    # и «что нашла последняя сверка» становится вопросом с догадкой.
    run_id: Mapped[str] = mapped_column(PgUUID(as_uuid=False))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    field: Mapped[str] = mapped_column(String(64))
    ours: Mapped[str | None] = mapped_column(String(512))
    theirs: Mapped[str | None] = mapped_column(String(512))
    action: Mapped[FindingAction] = mapped_column(
        Enum(FindingAction, name="reconciliation_action", native_enum=True)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

- [ ] **Шаг 5: Дописать экспорт и миграцию**

В `db/models/__init__.py` добавить `FindingAction`, `ReconciliationFinding`, `WebhookEvent`, `WebhookSource`, список `__all__` держать отсортированным.

```python
# backend/core/src/repibot_core/db/migrations/versions/0005_webhooks.py
"""События вебхуков и расхождения сверки.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

WEBHOOK_SOURCE = sa.Enum("remnawave", "yookassa", name="webhook_source")
FINDING_ACTION = sa.Enum("fixed", "skipped", name="reconciliation_action")


def upgrade() -> None:
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", WEBHOOK_SOURCE, nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source", "event_id", name="uq_webhook_events_source_id"),
    )

    op.create_table(
        "reconciliation_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("field", sa.String(64), nullable=False),
        sa.Column("ours", sa.String(512), nullable=True),
        sa.Column("theirs", sa.String(512), nullable=True),
        sa.Column("action", FINDING_ACTION, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Отчёт читается прогоном целиком, а не построчно.
    op.create_index(
        "ix_reconciliation_findings_run", "reconciliation_findings", ["run_id", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_findings_run", table_name="reconciliation_findings")
    op.drop_table("reconciliation_findings")
    op.drop_table("webhook_events")

    for enum_type in (FINDING_ACTION, WEBHOOK_SOURCE):
        enum_type.drop(op.get_bind(), checkfirst=True)
```

**Важно:** индексы и ограничения, объявленные в миграции, обязаны совпадать с `__table_args__` моделей — иначе `test_migrations_match_the_models` увидит дрейф автогенерации. В этапе 2a на этом уже спотыкались.

- [ ] **Шаг 6: Запустить тесты**

Запуск: `uv run pytest backend/core/tests/test_webhook_models.py backend/core/tests/test_migrations.py -q`
Ожидание: PASS. Фикстура `db_session` прогоняет `downgrade base` и `upgrade head`, то есть обратная миграция проверяется каждым запуском.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core/src/repibot_core/db backend/core/tests/test_webhook_models.py
git commit -m "feat: таблицы событий вебхуков и расхождений сверки"
```

---

### Задача 3: Фасады устройств и трафика

**Файлы:**
- Создать: `backend/core/src/repibot_core/integrations/remnawave/devices.py`
- Создать: `backend/core/src/repibot_core/integrations/remnawave/stats.py`
- Изменить: `backend/core/src/repibot_core/integrations/remnawave/__init__.py`
- Изменить: `backend/core/src/repibot_core/testing/remnawave.py`
- Тест: `backend/core/tests/test_remnawave_devices.py`

**Интерфейсы:**
- Потребляет: `PanelDevice`, `PanelUsage`, `DeleteDeviceBody` (задача 1), `RemnawaveClient` (2a).
- Отдаёт:
  - `PanelDevices(client)`: `list(panel_id: int) -> list[PanelDevice]`, `delete(panel_id: int, hwid: str) -> None`.
  - `PanelStats(client)`: `usage(panel_id: int, *, start: date, end: date) -> PanelUsage`.
  - `FakePanel` дополняется полем `devices: dict[int, list[dict[str, Any]]]`, методом `add_device(panel_id, hwid, *, platform=None, device_model=None)` и маршрутами устройств и трафика.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_remnawave_devices.py
"""Фасады устройств и трафика: адреса, тела запросов, разбор ответов."""

from __future__ import annotations

from datetime import date

import pytest

from repibot_core.integrations.remnawave.client import RemnawaveRejected
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.integrations.remnawave.stats import PanelStats
from repibot_core.testing.remnawave import FakePanel


async def test_devices_are_listed_for_user() -> None:
    panel = FakePanel()
    panel.add_device(7, "hwid-1", platform="iOS", device_model="iPhone 15")
    panel.add_device(7, "hwid-2", platform="Android", device_model=None)
    panel.add_device(9, "чужое", platform="Windows", device_model=None)

    devices = await PanelDevices(panel.client()).list(7)

    assert [device.hwid for device in devices] == ["hwid-1", "hwid-2"]
    assert devices[1].deviceModel is None


async def test_unknown_user_has_no_devices() -> None:
    """Пустой список, а не отказ: у нового пользователя устройств просто нет."""
    assert await PanelDevices(FakePanel().client()).list(404) == []


async def test_delete_sends_user_and_hwid_in_body() -> None:
    panel = FakePanel()
    panel.add_device(7, "hwid-1")

    await PanelDevices(panel.client()).delete(7, "hwid-1")

    assert panel.devices[7] == []
    assert ("POST", "/api/hwid/devices/delete") in panel.requests


async def test_delete_of_missing_device_is_rejected() -> None:
    """Панель отвечает отказом, и глушить его нельзя: сервис отличает чужой hwid."""
    panel = FakePanel()
    with pytest.raises(RemnawaveRejected):
        await PanelDevices(panel.client()).delete(7, "нет-такого")


async def test_usage_asks_for_the_given_range() -> None:
    panel = FakePanel()
    panel.add_usage(7, "2026-08-05", 1024)
    panel.add_usage(7, "2026-08-06", 2048)

    usage = await PanelStats(panel.client()).usage(
        7, start=date(2026, 8, 1), end=date(2026, 8, 6)
    )

    assert usage.categories == ["2026-08-05", "2026-08-06"]
    assert [point for series in usage.series for point in series.data] == [1024, 2048]
    method, path = panel.requests[-1]
    assert method == "GET"
    assert path == "/api/bandwidth-stats/users/7"
    assert panel.last_query == {"start": "2026-08-01", "end": "2026-08-06"}
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_remnawave_devices.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.integrations.remnawave.devices`

- [ ] **Шаг 3: Написать фасад устройств**

```python
# backend/core/src/repibot_core/integrations/remnawave/devices.py
"""Устройства пользователя в панели.

Панель считает привязанные устройства сама и режет доступ при превышении
лимита тарифа. Мы их не храним — читаем и удаляем по требованию.
"""

from __future__ import annotations

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import GetUserHwidDevicesResponseDto
from repibot_core.integrations.remnawave.types import DeleteDeviceBody, PanelDevice


class PanelDevices:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def list(self, panel_id: int) -> list[PanelDevice]:
        response = await self._client.request("GET", f"/api/hwid/devices/{panel_id}")
        # 404 — «устройств нет», а не отказ: у только что созданного
        # пользователя панели их и не должно быть.
        if response.status_code == httpx.codes.NOT_FOUND:
            return []
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
        return list(
            GetUserHwidDevicesResponseDto.model_validate_json(response.content).response.devices
        )

    async def delete(self, panel_id: int, hwid: str) -> None:
        body = DeleteDeviceBody(userId=panel_id, hwid=hwid)
        response = await self._client.request(
            "POST", "/api/hwid/devices/delete", content=body.model_dump_json()
        )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
```

- [ ] **Шаг 4: Написать фасад трафика**

```python
# backend/core/src/repibot_core/integrations/remnawave/stats.py
"""Потребление трафика по дням."""

from __future__ import annotations

from datetime import date

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient, RemnawaveRejected
from repibot_core.integrations.remnawave.models import GetStatsUserUsageResponseDto
from repibot_core.integrations.remnawave.types import PanelUsage


class PanelStats:
    def __init__(self, client: RemnawaveClient) -> None:
        self._client = client

    async def usage(self, panel_id: int, *, start: date, end: date) -> PanelUsage:
        """Обе границы обязательны: панель не подставляет период по умолчанию."""
        response = await self._client.request(
            "GET",
            f"/api/bandwidth-stats/users/{panel_id}",
            params={"start": start.isoformat(), "end": end.isoformat()},
        )
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise RemnawaveRejected(response.status_code, response.text[:500])
        return GetStatsUserUsageResponseDto.model_validate_json(response.content).response
```

В `integrations/remnawave/__init__.py` выставить наружу `PanelDevices` и `PanelStats`.

- [ ] **Шаг 5: Дополнить заглушку**

В `testing/remnawave.py`:

- поля `self.devices: dict[int, list[dict[str, Any]]] = {}`, `self.usage: dict[int, dict[str, float]] = {}`, `self.last_query: dict[str, str] = {}`;
- метод `add_device(panel_id, hwid, *, platform=None, os_version=None, device_model=None)` кладёт словарь со всеми обязательными полями ответа: `hwid`, `userId`, `platform`, `osVersion`, `deviceModel`, `userAgent`, `requestIp`, `createdAt`, `updatedAt`;
- метод `add_usage(panel_id, day, used_bytes)` наполняет `self.usage`;
- в `_handle` запомнить `self.last_query = dict(request.url.params)` и добавить маршруты:

```python
        if path.startswith("/api/hwid/devices/") and request.method == "GET":
            return self._devices(int(path.rsplit("/", 1)[-1]))
        if path == "/api/hwid/devices/delete":
            return self._delete_device(json.loads(request.content))
        if path.startswith("/api/bandwidth-stats/users/"):
            return self._usage(int(path.rsplit("/", 1)[-1]))
```

```python
    def _devices(self, panel_id: int) -> httpx.Response:
        devices = self.devices.get(panel_id, [])
        return httpx.Response(
            200, json={"response": {"total": len(devices), "devices": devices}}
        )

    def _delete_device(self, body: dict[str, Any]) -> httpx.Response:
        # int: идентификатор приходит числом и сериализуется как 7.0.
        panel_id = int(body["userId"])
        devices = self.devices.get(panel_id, [])
        remaining = [device for device in devices if device["hwid"] != body["hwid"]]
        if len(remaining) == len(devices):
            # Панель отвечает отказом на чужой или несуществующий hwid — от
            # этого зависит поведение сервиса, и заглушка обязана его повторять.
            return httpx.Response(404, json={"message": "device not found"})
        self.devices[panel_id] = remaining
        return httpx.Response(200, json={"response": {"isDeleted": True}})

    def _usage(self, panel_id: int) -> httpx.Response:
        days = self.usage.get(panel_id, {})
        categories = sorted(days)
        return httpx.Response(
            200,
            json={
                "response": {
                    "categories": categories,
                    "sparklineData": [days[day] for day in categories],
                    "topNodes": [],
                    "series": [
                        {
                            "uuid": "22222222-2222-4222-8222-222222222222",
                            "name": "Нода",
                            "color": "#000000",
                            "countryCode": "NL",
                            "total": sum(days.values()),
                            "data": [days[day] for day in categories],
                        }
                    ]
                    if categories
                    else [],
                }
            },
        )
```

Порядок проверок в `_handle` важен: маршрут `/api/users/{id}` уже существует и разбирает хвост пути как число, поэтому новые ветки не должны попадать под него.

- [ ] **Шаг 6: Запустить тесты**

Запуск: `uv run pytest backend/core/tests/test_remnawave_devices.py backend/core/tests/test_fake_panel.py backend/core/tests/test_provisioning.py -q`
Ожидание: PASS. Последние два набора — проверка, что правка заглушки не сломала этап 2a.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core/src/repibot_core/integrations/remnawave backend/core/src/repibot_core/testing backend/core/tests/test_remnawave_devices.py
git commit -m "feat: фасады устройств и трафика панели"
```

---

### Задача 4: Репозитории событий и расхождений

**Файлы:**
- Создать: `backend/core/src/repibot_core/db/repositories/webhooks.py`
- Создать: `backend/core/src/repibot_core/db/repositories/reconciliation.py`
- Тест: `backend/core/tests/test_webhook_repositories.py`

**Интерфейсы:**
- Потребляет: `WebhookEvent`, `ReconciliationFinding` (задача 2).
- Отдаёт:
  - `WebhookRepository(session)`: `remember(*, source, event_id, event, payload, now) -> WebhookEvent | None` — `None`, если событие уже принято; `mark_processed(event, now) -> None`.
  - `FindingRepository(session)`: `add(*, run_id, user_id, field, ours, theirs, action, now) -> ReconciliationFinding`; `latest_run() -> list[ReconciliationFinding]`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_webhook_repositories.py
"""Идемпотентность приёма и чтение последнего прогона сверки."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction, WebhookSource
from repibot_core.db.repositories.reconciliation import FindingRepository
from repibot_core.db.repositories.webhooks import WebhookRepository

pytestmark = pytest.mark.docker

RUN_ONE = "0f6a1c2e-0000-4000-8000-000000000001"
RUN_TWO = "0f6a1c2e-0000-4000-8000-000000000002"


async def test_second_delivery_returns_none(db_session: AsyncSession) -> None:
    """Повторная доставка не должна порождать вторую обработку."""
    repository = WebhookRepository(db_session)
    now = datetime.now(UTC)

    first = await repository.remember(
        source=WebhookSource.remnawave,
        event_id="user.expired:2026-08-06T12:00:00Z:42",
        event="user.expired",
        payload={"scope": "user"},
        now=now,
    )
    second = await repository.remember(
        source=WebhookSource.remnawave,
        event_id="user.expired:2026-08-06T12:00:00Z:42",
        event="user.expired",
        payload={"scope": "user"},
        now=now,
    )

    assert first is not None
    assert second is None


async def test_latest_run_returns_only_last(db_session: AsyncSession) -> None:
    """Отчёт читается прогоном целиком: смешанная лента не отвечает ни на что."""
    findings = FindingRepository(db_session)
    now = datetime.now(UTC)
    for run in (RUN_ONE, RUN_TWO):
        await findings.add(
            run_id=run,
            user_id=None,
            field="expireAt",
            ours="a",
            theirs="b",
            action=FindingAction.fixed,
            now=now,
        )

    rows = await findings.latest_run()
    assert [row.run_id for row in rows] == [RUN_TWO]
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_webhook_repositories.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.db.repositories.webhooks`

- [ ] **Шаг 3: Написать репозиторий событий**

```python
# backend/core/src/repibot_core/db/repositories/webhooks.py
"""Доступ к принятым вебхукам."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import WebhookEvent, WebhookSource


class WebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def remember(
        self,
        *,
        source: WebhookSource,
        event_id: str,
        event: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> WebhookEvent | None:
        """Записывает событие. `None` — такое уже принимали.

        Проверка запросом, а не перехватом ошибки уникальности: перехват
        оставил бы транзакцию в состоянии отката, и обработчику пришлось бы
        начинать её заново ради заведомо ненужной работы.
        """
        statement = select(WebhookEvent).where(
            WebhookEvent.source == source, WebhookEvent.event_id == event_id
        )
        if (await self._session.execute(statement)).scalar_one_or_none() is not None:
            return None

        row = WebhookEvent(
            source=source, event_id=event_id, event=event, payload=payload, received_at=now
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def mark_processed(self, event: WebhookEvent, now: datetime) -> None:
        event.processed_at = now
        await self._session.flush()
```

- [ ] **Шаг 4: Написать репозиторий расхождений**

```python
# backend/core/src/repibot_core/db/repositories/reconciliation.py
"""Доступ к расхождениям сверки."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction, ReconciliationFinding


class FindingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        run_id: str,
        user_id: int | None,
        field: str,
        ours: str | None,
        theirs: str | None,
        action: FindingAction,
        now: datetime,
    ) -> ReconciliationFinding:
        row = ReconciliationFinding(
            run_id=run_id,
            user_id=user_id,
            field=field,
            ours=ours,
            theirs=theirs,
            action=action,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest_run(self) -> list[ReconciliationFinding]:
        """Расхождения последнего прогона, у которого они были.

        Прогон без расхождений строк не оставляет, поэтому «последний прогон»
        определяется по последней записи, а не по времени запуска.
        """
        last = select(ReconciliationFinding.run_id).order_by(ReconciliationFinding.id.desc()).limit(1)
        run_id = (await self._session.execute(last)).scalar_one_or_none()
        if run_id is None:
            return []

        statement = (
            select(ReconciliationFinding)
            .where(ReconciliationFinding.run_id == run_id)
            .order_by(ReconciliationFinding.id)
        )
        return list((await self._session.execute(statement)).scalars())
```

- [ ] **Шаг 5: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_webhook_repositories.py -q`
Ожидание: PASS, 2 теста

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/db/repositories backend/core/tests/test_webhook_repositories.py
git commit -m "feat: репозитории вебхуков и расхождений сверки"
```

---

### Задача 5: Сервис устройств

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/devices.py`
- Тест: `backend/core/tests/test_device_service.py`

**Интерфейсы:**
- Потребляет: `PanelDevices` (3), `PanelCache` (пишет ведущий, см. ниже), `SubscriptionRepository`, `PlanRepository`, `UserRepository`, `ServiceError`.
- Отдаёт:
  - `DeviceView` — dataclass `(hwid, platform, device_model, os_version, created_at)`.
  - `DevicesView` — dataclass `(devices: list[DeviceView], limit: int, used: int)`.
  - `DeviceService(session, devices: PanelDevices, cache: PanelCache)`: `list(user_id) -> DevicesView`, `unlink(user_id, hwid) -> None`.

**`PanelCache` — готовый файл `backend/core/src/repibot_core/services/panel_cache.py`, написанный ведущим:**

```python
class PanelCache:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None
    async def get(self, key: str) -> Any | None      # разобранный JSON или None
    async def put(self, key: str, value: Any) -> None
    async def drop(self, key: str) -> None

def devices_key(user_id: int) -> str                 # panel:devices:{user_id}
def usage_key(user_id: int, start: date, end: date) -> str
```

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_device_service.py
"""Устройства: кэш, лимит тарифа, чужой hwid."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.services.devices import DeviceService
from repibot_core.services.errors import ServiceError
from repibot_core.services.panel_cache import PanelCache
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"


async def _subscriber(db_session: AsyncSession, *, panel_id: int, device_limit: int) -> User:
    plan = await PlanRepository(db_session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=0,
        traffic_reset_strategy=TrafficResetStrategy.NO_RESET,
        hwid_device_limit=device_limit,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="d@example.org", referral_code="dev00001", remnawave_id=panel_id)
    db_session.add(user)
    await db_session.flush()

    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await db_session.commit()
    return user


def _service(db_session: AsyncSession, panel: FakePanel) -> DeviceService:
    return DeviceService(
        db_session, PanelDevices(panel.client()), PanelCache(FakeRedis(), ttl_seconds=60)
    )


async def test_list_reports_limit_from_plan(db_session: AsyncSession) -> None:
    user = await _subscriber(db_session, panel_id=7, device_limit=3)
    panel = FakePanel()
    panel.add_device(7, "hwid-1", platform="iOS")

    view = await _service(db_session, panel).list(user.id)

    assert view.limit == 3
    assert view.used == 1
    assert view.devices[0].platform == "iOS"


async def test_second_call_does_not_hit_panel(db_session: AsyncSession) -> None:
    """Список устройств меняется редко, а экран кабинета опрашивают часто."""
    user = await _subscriber(db_session, panel_id=7, device_limit=3)
    panel = FakePanel()
    panel.add_device(7, "hwid-1")
    service = _service(db_session, panel)
    await service.list(user.id)

    panel.requests.clear()
    await service.list(user.id)

    assert panel.requests == []


async def test_unlink_drops_cache_immediately(db_session: AsyncSession) -> None:
    """Иначе человек жмёт «отвязать» и минуту видит удалённое устройство."""
    user = await _subscriber(db_session, panel_id=7, device_limit=3)
    panel = FakePanel()
    panel.add_device(7, "hwid-1")
    service = _service(db_session, panel)
    await service.list(user.id)

    await service.unlink(user.id, "hwid-1")

    assert (await service.list(user.id)).used == 0


async def test_unlink_of_foreign_device_is_refused(db_session: AsyncSession) -> None:
    """Проверка по ответу панели, а не по факту, что клиент прислал знакомый hwid."""
    user = await _subscriber(db_session, panel_id=7, device_limit=3)
    panel = FakePanel()
    panel.add_device(9, "чужое")

    with pytest.raises(ServiceError) as error:
        await _service(db_session, panel).unlink(user.id, "чужое")
    assert error.value.code == "device_not_found"


async def test_user_without_subscription_gets_service_error(db_session: AsyncSession) -> None:
    user = User(email="n@example.org", referral_code="dev00002")
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(ServiceError) as error:
        await _service(db_session, FakePanel()).list(user.id)
    assert error.value.code == "subscription_missing"
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_device_service.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.services.devices`

- [ ] **Шаг 3: Написать сервис**

```python
# backend/core/src/repibot_core/services/devices.py
"""Устройства пользователя.

Свои устройства человек отвязывает сам: иначе смена телефона превращается в
обращение в поддержку. Список читается из панели и кэшируется — экран кабинета
опрашивают часто, а меняется он редко.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.db.repositories.users import UserRepository
from repibot_core.integrations.remnawave.client import RemnawaveRejected
from repibot_core.integrations.remnawave.devices import PanelDevices
from repibot_core.services.errors import ServiceError
from repibot_core.services.panel_cache import PanelCache, devices_key


@dataclass(frozen=True, slots=True)
class DeviceView:
    hwid: str
    platform: str | None
    device_model: str | None
    os_version: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DevicesView:
    devices: list[DeviceView]
    limit: int
    used: int


class DeviceService:
    def __init__(
        self, session: AsyncSession, devices: PanelDevices, cache: PanelCache
    ) -> None:
        self._session = session
        self._panel = devices
        self._cache = cache
        self._users = UserRepository(session)
        self._subscriptions = SubscriptionRepository(session)
        self._plans = PlanRepository(session)

    async def list(self, user_id: int) -> DevicesView:
        panel_id, limit = await self._context(user_id)
        raw = await self._cached(user_id, panel_id)
        devices = [_view(item) for item in raw]
        return DevicesView(devices=devices, limit=limit, used=len(devices))

    async def unlink(self, user_id: int, hwid: str) -> None:
        panel_id, _ = await self._context(user_id)
        try:
            await self._panel.delete(panel_id, hwid)
        except RemnawaveRejected as error:
            # Панель отвечает отказом и на чужой hwid, и на несуществующий.
            # Различать их незачем: для человека это одно и то же — «такого
            # устройства у вас нет».
            msg = "устройство не найдено"
            raise ServiceError(msg, "device_not_found") from error

        # Кэш гасится сразу, а не по истечении срока: иначе человек нажимает
        # кнопку и ещё минуту видит удалённое устройство в списке.
        await self._cache.drop(devices_key(user_id))

    async def _context(self, user_id: int) -> tuple[int, int]:
        """Идентификатор в панели и лимит устройств тарифа."""
        user = await self._users.get(user_id)
        subscription = await self._subscriptions.get_for_user(user_id)
        if user is None or user.remnawave_id is None or subscription is None:
            msg = "подписки нет, устройств тоже"
            raise ServiceError(msg, "subscription_missing")

        plan = await self._plans.get(subscription.plan_id)
        limit = plan.hwid_device_limit if plan is not None else 0
        return user.remnawave_id, limit

    async def _cached(self, user_id: int, panel_id: int) -> list[dict[str, Any]]:
        key = devices_key(user_id)
        stored = await self._cache.get(key)
        if isinstance(stored, list):
            return stored

        fresh = [device.model_dump(mode="json") for device in await self._panel.list(panel_id)]
        await self._cache.put(key, fresh)
        return fresh


def _view(item: dict[str, Any]) -> DeviceView:
    return DeviceView(
        hwid=str(item["hwid"]),
        platform=item.get("platform"),
        device_model=item.get("deviceModel"),
        os_version=item.get("osVersion"),
        created_at=datetime.fromisoformat(str(item["createdAt"])),
    )
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_device_service.py -q`
Ожидание: PASS, 5 тестов

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/services/devices.py backend/core/tests/test_device_service.py
git commit -m "feat: список и отвязка устройств с кэшем"
```

---

### Задача 6: Сервис трафика

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/traffic.py`
- Тест: `backend/core/tests/test_traffic_service.py`

**Интерфейсы:**
- Потребляет: `PanelStats` и `PanelUsers` (3 и 2a), `PanelCache`, репозитории подписок и тарифов.
- Отдаёт:
  - `TrafficDay` — dataclass `(day: date, used_bytes: int)`.
  - `TrafficView` — dataclass `(used_bytes: int, lifetime_bytes: int, limit_bytes: int, days: list[TrafficDay])`.
  - `TrafficService(session, users: PanelUsers, stats: PanelStats, cache: PanelCache)`: `current(user_id, *, days: int = 30, today: date | None = None) -> TrafficView`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_traffic_service.py
"""Трафик: текущий период, разбивка по дням, кэш."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.stats import PanelStats
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.errors import ServiceError
from repibot_core.services.panel_cache import PanelCache
from repibot_core.services.traffic import TrafficService
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

SQUAD = "11111111-1111-4111-8111-111111111111"
TODAY = date(2026, 8, 6)


async def _subscriber(db_session: AsyncSession, *, panel_id: int, limit: int) -> User:
    plan = await PlanRepository(db_session).create(
        code="month",
        name={"ru": "Месяц", "en": "Month"},
        description=None,
        duration_days=30,
        price_rub=Decimal("299.00"),
        price_stars=199,
        traffic_limit_bytes=limit,
        traffic_reset_strategy=TrafficResetStrategy.MONTH,
        hwid_device_limit=3,
        internal_squad_uuids=[SQUAD],
        is_trial=False,
        is_active=True,
        is_visible=True,
        sort_order=0,
    )
    user = User(email="t@example.org", referral_code="trf00001", remnawave_id=panel_id)
    db_session.add(user)
    await db_session.flush()

    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await db_session.commit()
    return user


def _service(db_session: AsyncSession, panel: FakePanel) -> TrafficService:
    client = panel.client()
    return TrafficService(
        db_session, PanelUsers(client), PanelStats(client), PanelCache(FakeRedis(), ttl_seconds=60)
    )


async def test_days_are_summed_across_nodes(db_session: AsyncSession) -> None:
    """Человеку нужен трафик за день, а не разбивка по нодам."""
    user = await _subscriber(db_session, panel_id=1, limit=1024)
    panel = FakePanel()
    await _create_panel_user(panel)
    panel.add_usage(1, "2026-08-05", 100)
    panel.add_usage(1, "2026-08-06", 250)

    view = await _service(db_session, panel).current(user.id, days=7, today=TODAY)

    assert [(day.day, day.used_bytes) for day in view.days] == [
        (date(2026, 8, 5), 100),
        (date(2026, 8, 6), 250),
    ]
    assert view.limit_bytes == 1024


async def test_second_call_does_not_hit_panel(db_session: AsyncSession) -> None:
    user = await _subscriber(db_session, panel_id=1, limit=0)
    panel = FakePanel()
    await _create_panel_user(panel)
    service = _service(db_session, panel)
    await service.current(user.id, today=TODAY)

    panel.requests.clear()
    await service.current(user.id, today=TODAY)

    assert panel.requests == []


async def test_user_without_panel_id_gets_service_error(db_session: AsyncSession) -> None:
    user = User(email="np@example.org", referral_code="trf00002")
    db_session.add(user)
    await db_session.commit()

    with pytest.raises(ServiceError) as error:
        await _service(db_session, FakePanel()).current(user.id, today=TODAY)
    assert error.value.code == "subscription_missing"


async def _create_panel_user(panel: FakePanel) -> None:
    """Пользователь в панели нужен ради userTraffic в его объекте."""
    from datetime import UTC, datetime

    from repibot_core.integrations.remnawave.types import CreateUserBody

    await PanelUsers(panel.client()).create(
        CreateUserBody(username="rp_1", expireAt=datetime(2026, 9, 6, 12, tzinfo=UTC))
    )
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_traffic_service.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.services.traffic`

- [ ] **Шаг 3: Написать сервис**

Ключевые решения, которые обязаны попасть в код:

1. Текущее потребление и накопленное берутся из объекта пользователя
   (`userTraffic.usedTrafficBytes`, `lifetimeUsedTrafficBytes`), разбивка по
   дням — из `PanelStats.usage`. Два запроса, оба под одним кэшем: разъезд
   между цифрой сверху экрана и суммой столбиков выглядит как ошибка счёта.
2. День — сумма по всем нодам: `sum(series[i].data[index] for series)`.
   `sparklineData` не используется — в схеме нигде не сказано, что это именно
   сумма, а гадать о смысле чужого поля дороже, чем сложить самому.
3. Период по умолчанию — 30 дней назад от `today`. Параметр `today`
   существует ради тестов: без него набор зависел бы от даты прогона.
4. Пустой ответ панели — это `days: []`, а не ошибка: у нового пользователя
   трафика ещё нет.

```python
    async def current(
        self, user_id: int, *, days: int = 30, today: date | None = None
    ) -> TrafficView:
        panel_id, limit = await self._context(user_id)
        end = today or datetime.now(UTC).date()
        start = end - timedelta(days=days)

        cached = await self._cache.get(usage_key(user_id, start, end))
        if cached is not None:
            return _restore(cached, limit)

        user = await self._panel.get(panel_id)
        if user is None:
            msg = "пользователя нет в панели"
            raise ServiceError(msg, "subscription_missing")

        usage = await self._stats.usage(panel_id, start=start, end=end)
        view = TrafficView(
            used_bytes=int(user.userTraffic.usedTrafficBytes),
            lifetime_bytes=int(user.userTraffic.lifetimeUsedTrafficBytes),
            limit_bytes=limit,
            days=[
                TrafficDay(
                    day=date.fromisoformat(category),
                    used_bytes=int(sum(series.data[index] for series in usage.series)),
                )
                for index, category in enumerate(usage.categories)
            ],
        )
        await self._cache.put(usage_key(user_id, start, end), _dump(view))
        return view
```

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_traffic_service.py -q`
Ожидание: PASS, 3 теста

- [ ] **Шаг 5: Коммит**

```bash
git add backend/core/src/repibot_core/services/traffic.py backend/core/tests/test_traffic_service.py
git commit -m "feat: потребление трафика с разбивкой по дням"
```

---

### Задача 7: Сервис вебхуков панели

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/panel_webhooks.py`
- Тест: `backend/core/tests/test_panel_webhooks.py`

**Интерфейсы:**
- Потребляет: `WebhookRepository` (4), `SubscriptionRepository`, `UserRepository`, `OutboxRepository`, `TOPIC_PROVISION` (2a), `PanelCache`.
- Отдаёт:
  - `verify_signature(secret: str, body: bytes, header: str | None) -> bool`.
  - `PanelWebhookService(session, cache)`: `handle(payload: dict[str, Any], *, now: datetime | None = None) -> bool` — `False`, если событие уже принимали.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_panel_webhooks.py
"""Приём событий панели: подпись, дедупликация, реакции."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import OutboxMessage, SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.services.panel_cache import PanelCache, devices_key
from repibot_core.services.panel_webhooks import PanelWebhookService, verify_signature
from repibot_core.services.provisioning import TOPIC_PROVISION

pytestmark = pytest.mark.docker

SECRET = "секрет-панели"


def _signed(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_signature_is_checked_over_raw_body() -> None:
    body = json.dumps({"scope": "user"}, ensure_ascii=False).encode()
    assert verify_signature(SECRET, body, _signed(body)) is True
    assert verify_signature(SECRET, body, _signed(b"другое")) is False
    assert verify_signature(SECRET, body, None) is False


def test_empty_secret_never_verifies() -> None:
    """Пустой секрет означает «вебхуки не настроены», а не «принимай всё»."""
    body = b"{}"
    assert verify_signature("", body, hmac.new(b"", body, hashlib.sha256).hexdigest()) is False


async def _subscriber(db_session: AsyncSession) -> User:
    plan = await PlanRepository(db_session).create(
        code="month",
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
    user = User(email="w@example.org", referral_code="whk00001", remnawave_id=42)
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await db_session.commit()
    return user


def _event(event: str, *, scope: str = "user", panel_id: int = 42) -> dict[str, object]:
    data: dict[str, object] = (
        {"id": panel_id} if scope == "user" else {"user": {"id": panel_id}, "device": {}}
    )
    return {
        "scope": scope,
        "event": event,
        "timestamp": "2026-08-06T12:00:00Z",
        "data": data,
    }


async def test_repeated_delivery_is_ignored(db_session: AsyncSession) -> None:
    await _subscriber(db_session)
    service = PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60))

    assert await service.handle(_event("user.revoked")) is True
    assert await service.handle(_event("user.revoked")) is False


async def test_state_event_queues_reconcile(db_session: AsyncSession) -> None:
    """Панель изменили мимо нас — надо привести её обратно к нашему состоянию."""
    await _subscriber(db_session)
    service = PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60))

    await service.handle(_event("user.revoked"))

    queued = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert [message.topic for message in queued] == [TOPIC_PROVISION]


async def test_device_event_drops_cache(db_session: AsyncSession) -> None:
    user = await _subscriber(db_session)
    redis = FakeRedis()
    cache = PanelCache(redis, ttl_seconds=60)
    await cache.put(devices_key(user.id), [{"hwid": "старое"}])

    await PanelWebhookService(db_session, cache).handle(
        _event("user_hwid_devices.added", scope="user_hwid_devices")
    )

    assert await cache.get(devices_key(user.id)) is None


async def test_expiry_event_does_not_move_our_date(db_session: AsyncSession) -> None:
    """Вебхук — повод посмотреть, а не источник биллинга."""
    user = await _subscriber(db_session)
    before = await SubscriptionRepository(db_session).get_for_user(user.id)
    assert before is not None
    expires_at = before.expires_at

    await PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60)).handle(
        _event("user.expired")
    )

    await db_session.refresh(before)
    assert before.expires_at == expires_at


async def test_unknown_event_is_stored_and_ignored(db_session: AsyncSession) -> None:
    """Панель обновится раньше нас; незнакомое событие не должно валить приём."""
    await _subscriber(db_session)
    service = PanelWebhookService(db_session, PanelCache(FakeRedis(), ttl_seconds=60))

    assert await service.handle(_event("user.какое-то-новое")) is True
    queued = (await db_session.execute(select(OutboxMessage))).scalars().all()
    assert queued == []
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_panel_webhooks.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.services.panel_webhooks`

- [ ] **Шаг 3: Написать проверку подписи**

```python
def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Подпись сверяется по сырому телу, до разбора JSON.

    Пересобранный из объекта JSON отличается от присланного пробелами и
    порядком ключей, и подпись перестала бы сходиться на ровном месте.

    Пустой секрет означает «вебхуки не настроены»: принимать неподписанные
    события опаснее, чем не принимать никаких.
    """
    if not secret or header is None:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # compare_digest, а не ==: сравнение за постоянное время не даёт подобрать
    # подпись по времени ответа.
    return hmac.compare_digest(expected, header.strip().removeprefix("sha256="))
```

- [ ] **Шаг 4: Написать сервис**

Состав:

```python
# События, после которых панель может расходиться с нашим состоянием.
_RECONCILE = frozenset(
    {
        "user.revoked",
        "user.modified",
        "user.deleted",
        "user.disabled",
        "user.enabled",
        "user.limited",
        "user.expired",
    }
)
_DEVICES = frozenset({"user_hwid_devices.added", "user_hwid_devices.deleted"})
```

`handle` делает по порядку:

1. Собирает `event_id` как `f"{event}:{timestamp}:{panel_id}"`, где `panel_id`
   берётся из `data.id` для событий пользователя и из `data.user.id` для
   событий устройств; при отсутствии — пустая строка.
2. `WebhookRepository.remember(...)`; `None` — возвращает `False` и ничего не
   делает.
3. Находит нашего пользователя по `remnawave_id`. Не нашёлся — событие
   сохраняется и помечается обработанным: это пользователь панели, заведённый
   мимо нас, и трогать его нельзя.
4. Реакция: событие из `_RECONCILE` кладёт задачу `TOPIC_PROVISION` в
   `outbox`; событие из `_DEVICES` гасит кэш устройств; остальные только
   записываются.
5. `mark_processed`, `commit`, возвращает `True`.

**Дату окончания не двигает ни одно событие.** Это правило архитектуры, и в
коде оно должно быть видно комментарием, а не подразумеваться.

- [ ] **Шаг 5: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/core/tests/test_panel_webhooks.py -q`
Ожидание: PASS, 7 тестов

- [ ] **Шаг 6: Коммит**

```bash
git add backend/core/src/repibot_core/services/panel_webhooks.py backend/core/tests/test_panel_webhooks.py
git commit -m "feat: приём и обработка событий панели"
```

---

### Задача 8: Клиентское API устройств и трафика

**Файлы:**
- Изменить: `backend/api/src/repibot_api/routers/subscription.py`
- Изменить: `backend/api/src/repibot_api/subscription_view.py`
- Изменить: `backend/api/src/repibot_api/schemas.py`
- Изменить: `backend/core/src/repibot_core/ratelimit.py`
- Тест: `backend/api/tests/test_devices_api.py`

**Интерфейсы:**
- Потребляет: `DeviceService` (5), `TrafficService` (6).
- Отдаёт: маршруты `GET /api/me/devices`, `POST /api/me/devices/unlink`, `GET /api/me/traffic`; схемы `DeviceResponse`, `DevicesResponse`, `UnlinkDeviceRequest`, `TrafficDayResponse`, `TrafficResponse`; правило `DEVICE_UNLINK_PER_USER`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/api/tests/test_devices_api.py
"""Устройства и трафик глазами клиента."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker


async def test_devices_need_subscription(
    api_client: AsyncClient, telegram_user_headers: dict[str, str]
) -> None:
    """Без подписки устройств нет — это 404, а не пустой список."""
    response = await api_client.get("/api/me/devices", headers=telegram_user_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "subscription_missing"


async def test_devices_are_listed_with_limit(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_subscriber: str
) -> None:
    response = await api_client.get("/api/me/devices", headers=telegram_user_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] >= 0
    assert body["used"] == len(body["devices"])


async def test_unlink_of_foreign_device_is_not_found(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_subscriber: str
) -> None:
    response = await api_client.post(
        "/api/me/devices/unlink", json={"hwid": "чужое"}, headers=telegram_user_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "device_not_found"


async def test_unlink_is_rate_limited(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_subscriber: str
) -> None:
    """Ограничение защищает не нас, а панель: без него лимит устройств обходится циклом."""
    last = None
    for _ in range(12):
        last = await api_client.post(
            "/api/me/devices/unlink", json={"hwid": "чужое"}, headers=telegram_user_headers
        )
    assert last is not None
    assert last.status_code == 429
    assert last.headers["retry-after"]


async def test_traffic_returns_limit_and_days(
    api_client: AsyncClient, telegram_user_headers: dict[str, str], trial_subscriber: str
) -> None:
    response = await api_client.get("/api/me/traffic", headers=telegram_user_headers)
    assert response.status_code == 200
    body = response.json()
    assert "used_bytes" in body
    assert isinstance(body["days"], list)


async def test_anonymous_sees_nothing(api_client: AsyncClient) -> None:
    assert (await api_client.get("/api/me/devices")).status_code == 401
    assert (await api_client.get("/api/me/traffic")).status_code == 401
```

Фикстура `trial_subscriber` добавляется в корневой `conftest.py`: активирует триал через API на пользователе `telegram_user_headers` при поднятой заглушке панели и возвращает его `subscription_url`. Фикстуры `telegram_user_headers`, `trial_plan`, `fake_panel` уже есть с этапа 2a.

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/api/tests/test_devices_api.py -q`
Ожидание: FAIL, 404 на `/api/me/devices`

- [ ] **Шаг 3: Добавить правило ограничения**

В `ratelimit.py`:

```python
# Отвязка устройства защищает не нас, а панель: без ограничения скрипт крутит
# отвязку в цикле и обходит лимит устройств тарифа. Значение берётся из
# настроек, поэтому правило собирается на месте вызова, а не объявляется здесь
# константой.
DEVICE_UNLINK_WINDOW = timedelta(days=1)
```

- [ ] **Шаг 4: Добавить схемы**

```python
class DeviceResponse(BaseModel):
    hwid: str
    platform: str | None
    device_model: str | None
    os_version: str | None
    created_at: datetime


class DevicesResponse(BaseModel):
    devices: list[DeviceResponse]
    limit: int
    used: int


class UnlinkDeviceRequest(BaseModel):
    # В теле, а не в пути: hwid приходит от клиента произвольной строкой и в
    # сегменте адреса ломается.
    hwid: str = Field(min_length=1, max_length=255)


class TrafficDayResponse(BaseModel):
    day: date
    used_bytes: int


class TrafficResponse(BaseModel):
    used_bytes: int
    lifetime_bytes: int
    limit_bytes: int
    days: list[TrafficDayResponse]
```

- [ ] **Шаг 5: Написать маршруты**

В `subscription_view.py` добавить зависимости `device_service` и `traffic_service` — собираются так же, как `subscription_service`, с закрытием клиента панели в `finally`.

В `routers/subscription.py`:

```python
@router.get("/api/me/devices", response_model=DevicesResponse)
async def my_devices(
    devices: Annotated[DeviceService, Depends(device_service)],
    context: Annotated[AuthContext, Depends(current_context)],
) -> DevicesResponse:
    try:
        view = await devices.list(context.principal.user_id)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        # Карточка подписки рисуется целиком: данные о ней лежат у нас, и
        # терять весь экран из-за чужого отказа нечестно. Недоступен только
        # блок устройств.
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
    return DevicesResponse(
        devices=[_device(item) for item in view.devices], limit=view.limit, used=view.used
    )


@router.post("/api/me/devices/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_device(
    payload: UnlinkDeviceRequest,
    devices: Annotated[DeviceService, Depends(device_service)],
    context: Annotated[AuthContext, Depends(current_context)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    settings = get_settings()
    await _enforce(
        redis,
        f"device-unlink:{context.principal.user_id}",
        Rule(limit=settings.device_unlink_limit_per_day, window=DEVICE_UNLINK_WINDOW),
    )
    try:
        await devices.unlink(context.principal.user_id, payload.hwid)
    except ServiceError as error:
        raise api_error_from_service(error) from error
    except RemnawaveUnavailable as error:
        raise ApiError("панель недоступна", 503, "panel_unavailable") from error
```

`_enforce` — та же функция, что в `routers/auth.py`: считает попытку и отвечает `429` с заголовком `Retry-After`. Если она там приватная, вынести её в `repibot_api/limits.py` и импортировать в оба роутера, а не копировать.

Маршрут `GET /api/me/traffic` пишется по тому же образцу и возвращает `TrafficResponse`.

- [ ] **Шаг 6: Запустить тест и убедиться, что он проходит**

Запуск: `uv run pytest backend/api/tests -q`
Ожидание: PASS, включая наборы этапа 2a.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/api backend/core/src/repibot_core/ratelimit.py conftest.py
git commit -m "feat: устройства и трафик в клиентском API"
```

---

### Задача 9: Приёмник вебхуков панели

**Файлы:**
- Создать: `backend/api/src/repibot_api/routers/webhooks.py`
- Изменить: `backend/api/src/repibot_api/main.py`
- Изменить: `docker/nginx.conf`
- Изменить: `tools/tests/test_nginx_conf.py`
- Тест: `backend/api/tests/test_panel_webhook_endpoint.py`

**Интерфейсы:**
- Потребляет: `PanelWebhookService`, `verify_signature` (7).
- Отдаёт: маршрут `POST /webhook/remnawave`.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/api/tests/test_panel_webhook_endpoint.py
"""Приёмник событий панели."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

from repibot_core.settings import get_settings

pytestmark = pytest.mark.docker

SECRET = "секрет-панели-для-тестов"


def _body(event: str = "user.revoked") -> bytes:
    return json.dumps(
        {
            "scope": "user",
            "event": event,
            "timestamp": "2026-08-06T12:00:00Z",
            "data": {"id": 42},
        },
        ensure_ascii=False,
    ).encode()


def _sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def panel_webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REMNAWAVE_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_signed_event_is_accepted(
    api_client: AsyncClient, panel_webhook_secret: None
) -> None:
    body = _body()
    response = await api_client.post(
        "/webhook/remnawave",
        content=body,
        headers={"content-type": "application/json", "x-remnawave-signature": _sign(body)},
    )
    assert response.status_code == 204


async def test_wrong_signature_is_refused(
    api_client: AsyncClient, panel_webhook_secret: None
) -> None:
    body = _body()
    response = await api_client.post(
        "/webhook/remnawave",
        content=body,
        headers={"content-type": "application/json", "x-remnawave-signature": _sign(b"чужое")},
    )
    assert response.status_code == 403


async def test_missing_signature_is_refused(
    api_client: AsyncClient, panel_webhook_secret: None
) -> None:
    response = await api_client.post(
        "/webhook/remnawave", content=_body(), headers={"content-type": "application/json"}
    )
    assert response.status_code == 403


async def test_unconfigured_secret_refuses_everything(api_client: AsyncClient) -> None:
    """Пустой секрет — «вебхуки не настроены», а не «принимай что угодно»."""
    body = _body()
    response = await api_client.post(
        "/webhook/remnawave",
        content=body,
        headers={"content-type": "application/json", "x-remnawave-signature": _sign(body)},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "webhooks_disabled"


async def test_repeated_delivery_is_still_ok(
    api_client: AsyncClient, panel_webhook_secret: None
) -> None:
    """Повтор не обрабатывается второй раз, но и ошибкой не считается.

    Панель на ошибку ответит новой попыткой, и приём зациклится.
    """
    body = _body()
    headers = {"content-type": "application/json", "x-remnawave-signature": _sign(body)}
    first = await api_client.post("/webhook/remnawave", content=body, headers=headers)
    second = await api_client.post("/webhook/remnawave", content=body, headers=headers)
    assert (first.status_code, second.status_code) == (204, 204)
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/api/tests/test_panel_webhook_endpoint.py -q`
Ожидание: FAIL, 404 на `/webhook/remnawave`

- [ ] **Шаг 3: Написать роутер**

```python
# backend/api/src/repibot_api/routers/webhooks.py
"""Входящие вебхуки внешних систем.

Секрета в адресе нет: URL целиком попадает в журналы прокси и мониторинга.
Источник подтверждается подписью тела.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import db_session, get_redis
from repibot_api.errors import ApiError
from repibot_core.services.panel_cache import PanelCache
from repibot_core.services.panel_webhooks import PanelWebhookService, verify_signature
from repibot_core.settings import get_settings

router = APIRouter(tags=["webhooks"])


@router.post("/webhook/remnawave", status_code=status.HTTP_204_NO_CONTENT)
async def remnawave_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(db_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    settings = get_settings()
    secret = settings.remnawave_webhook_secret.get_secret_value()
    if not secret:
        raise ApiError("вебхуки панели не настроены", 503, "webhooks_disabled")

    # Сырое тело, а не разобранный объект: пересобранный JSON отличается от
    # присланного пробелами и порядком ключей, и подпись не сойдётся.
    body = await request.body()
    if not verify_signature(secret, body, request.headers.get(settings.remnawave_webhook_header)):
        raise ApiError("подпись не сошлась", 403, "forbidden")

    cache = PanelCache(redis, ttl_seconds=settings.panel_cache_ttl_seconds)
    await PanelWebhookService(session, cache).handle(await request.json())
    # Повтор не ошибка: на ошибку панель ответит новой попыткой, и приём
    # зациклится на событии, которое мы уже обработали.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

Подключить роутер в `main.py`.

- [ ] **Шаг 4: Добавить маршрут в nginx**

В `docker/nginx.conf` рядом с `location = /webhook/telegram`:

```nginx
    # Событие панели подтверждается HMAC-подписью тела; имя заголовка задаётся
    # в её настройках и переносится в REMNAWAVE_WEBHOOK_HEADER.
    location = /webhook/remnawave {
        proxy_pass http://api_upstream;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
```

В `tools/tests/test_nginx_conf.py` дописать проверку, что маршрут объявлен поимённо и уходит в `api_upstream`, — по образцу уже существующей проверки для `/webhook/telegram`.

- [ ] **Шаг 5: Запустить тесты**

Запуск: `uv run pytest backend/api/tests/test_panel_webhook_endpoint.py tools/tests/test_nginx_conf.py -q`
Ожидание: PASS

- [ ] **Шаг 6: Коммит**

```bash
git add backend/api docker/nginx.conf tools/tests/test_nginx_conf.py
git commit -m "feat: приёмник вебхуков панели и маршрут nginx"
```

---

### Задача 10: Реконсиляция по расписанию

**Файлы:**
- Изменить: `backend/core/src/repibot_core/services/provisioning.py`
- Создать: `backend/core/src/repibot_core/services/reconciliation.py`
- Изменить: `backend/core/src/repibot_core/tasks.py`
- Тест: `backend/core/tests/test_reconciliation.py`

**Интерфейсы:**
- Потребляет: `ProvisioningService` (2a), `FindingRepository` (4), `SubscriptionRepository.list_for_reconcile` (2a).
- Отдаёт:
  - `Difference` — dataclass `(field: str, ours: str, theirs: str)` в `provisioning.py`.
  - `PanelState` получает поле `differences: tuple[Difference, ...] = ()`.
  - `ReconciliationService(session, provisioning)`: `run(*, run_id: str, limit: int = 100) -> int` — число записанных расхождений.
  - Задача `reconcile_panel()` с расписанием из `RECONCILE_INTERVAL_HOURS`.

**Почему поле в `PanelState`, а не отдельный метод:** примирение уже знает, что разошлось, — это его внутренняя работа. Второй метод, повторяющий сравнение, разошёлся бы с первым при первой же правке. Существующие вызывающие поле игнорируют, поэтому изменение никого не ломает.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_reconciliation.py
"""Сверка: расхождение записывается, чужой тег не правится."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_core.db.models import FindingAction, SubscriptionSource, TrafficResetStrategy, User
from repibot_core.db.repositories.plans import PlanRepository
from repibot_core.db.repositories.reconciliation import FindingRepository
from repibot_core.db.repositories.subscriptions import SubscriptionRepository
from repibot_core.domain.subscriptions import SubscriptionState
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.services.provisioning import ProvisioningService
from repibot_core.services.reconciliation import ReconciliationService
from repibot_core.testing.remnawave import FakePanel

pytestmark = pytest.mark.docker

RUN = "0f6a1c2e-0000-4000-8000-000000000001"


async def _subscriber(db_session: AsyncSession) -> User:
    plan = await PlanRepository(db_session).create(
        code="month",
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
    user = User(email="r@example.org", referral_code="rec00001")
    db_session.add(user)
    await db_session.flush()

    now = datetime.now(UTC)
    await SubscriptionRepository(db_session).create(
        user_id=user.id,
        plan_id=plan.id,
        status=SubscriptionState.active,
        started_at=now,
        expires_at=now + timedelta(days=30),
        source=SubscriptionSource.purchase,
    )
    await db_session.commit()
    return user


async def test_run_without_differences_writes_nothing(db_session: AsyncSession) -> None:
    """Сошлось — писать нечего. Отчёт не должен превращаться в шум."""
    user = await _subscriber(db_session)
    panel = FakePanel()
    provisioning = ProvisioningService(db_session, PanelUsers(panel.client()))
    await provisioning.reconcile(user.id)

    written = await ReconciliationService(db_session, provisioning).run(run_id=RUN)

    assert written == 0
    assert await FindingRepository(db_session).latest_run() == []


async def test_manual_change_in_panel_is_recorded_and_fixed(db_session: AsyncSession) -> None:
    """Расхождение обычно значит ручную правку админа — о ней надо знать."""
    user = await _subscriber(db_session)
    panel = FakePanel()
    provisioning = ProvisioningService(db_session, PanelUsers(panel.client()))
    state = await provisioning.reconcile(user.id)
    panel.users[state.panel_id]["hwidDeviceLimit"] = 99

    written = await ReconciliationService(db_session, provisioning).run(run_id=RUN)

    findings = await FindingRepository(db_session).latest_run()
    assert written == len(findings) >= 1
    limit_finding = next(row for row in findings if row.field == "hwidDeviceLimit")
    assert limit_finding.action is FindingAction.fixed
    assert limit_finding.theirs == "99"
    assert panel.users[state.panel_id]["hwidDeviceLimit"] == 3


async def test_foreign_tag_is_skipped_not_overwritten(db_session: AsyncSession) -> None:
    """Пользователя панели, заведённого мимо нас, автоматика не трогает."""
    user = await _subscriber(db_session)
    panel = FakePanel()
    provisioning = ProvisioningService(db_session, PanelUsers(panel.client()))
    state = await provisioning.reconcile(user.id)
    panel.users[state.panel_id]["tag"] = "РУЧНОЙ"
    panel.users[state.panel_id]["hwidDeviceLimit"] = 99

    await ReconciliationService(db_session, provisioning).run(run_id=RUN)

    findings = await FindingRepository(db_session).latest_run()
    assert [row.action for row in findings] == [FindingAction.skipped]
    assert panel.users[state.panel_id]["hwidDeviceLimit"] == 99
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_reconciliation.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.services.reconciliation`

- [ ] **Шаг 3: Научить примирение отчитываться**

В `provisioning.py`:

```python
@dataclass(frozen=True, slots=True)
class Difference:
    """Одно расхождение: что разошлось и каким было с обеих сторон."""

    field: str
    ours: str
    theirs: str


@dataclass(frozen=True, slots=True)
class PanelState:
    panel_id: int
    short_uuid: str
    subscription_url: str
    # Пустой кортеж по умолчанию: выдача доступа расхождениями не
    # интересуется, а сверке они нужны целиком.
    differences: tuple[Difference, ...] = ()
```

`_update_if_needed` уже строит словари `current` и `wanted`. Расхождения снимаются оттуда же, одним проходом, и возвращаются вместе с пользователем:

```python
    @staticmethod
    def _diff(current: dict[str, Any], wanted: dict[str, Any]) -> tuple[Difference, ...]:
        """Расхождения между панелью и нашим состоянием.

        Строками, а не значениями: отчёт читает человек, и `expireAt` в нём
        должен выглядеть датой, а не объектом Python.
        """
        return tuple(
            Difference(field=field, ours=str(wanted[field]), theirs=str(value))
            for field, value in current.items()
            if value != wanted[field]
        )

    async def _update_if_needed(
        self, existing: PanelUser, desired: dict[str, Any]
    ) -> tuple[PanelUser, tuple[Difference, ...], bool]:
        current, wanted = self._compare(existing, desired)
        differences = self._diff(current, wanted)

        if existing.tag != PANEL_TAG:
            # Пользователь панели заведён мимо нас: расхождения записываем,
            # но не правим. Автоматика не должна затирать ручную работу админа.
            logger.warning(
                "пользователь панели заведён мимо нас, правка пропущена",
                extra={"panel_user_id": existing.id, "tag": existing.tag},
            )
            return existing, differences, True

        if not differences:
            return existing, (), False

        updated = await self._panel.update(UpdateUserBody(id=int(existing.id), **desired))
        return updated, differences, False
```

Сборка словарей `current` и `wanted` выносится из `_update_if_needed` в `_compare`, чтобы сравнение было написано один раз: округление даты до секунды и приведение `trafficLimitBytes` к `float` уже живут там и повторяться не должны.

`reconcile` кладёт полученное в `PanelState`:

```python
        panel_user, differences, skipped = (
            (await self._create(username, user.telegram_id, user.email, desired), (), False)
            if existing is None
            else await self._update_if_needed(existing, desired)
        )
```

Публичный контракт не меняется: `reconcile` по-прежнему отдаёт `PanelState`, а выдача доступа новые поля просто не читает.

- [ ] **Шаг 4: Написать сервис сверки**

```python
# backend/core/src/repibot_core/services/reconciliation.py
"""Сверка нашего состояния с панелью.

Молчаливое исправление недопустимо: расхождение обычно означает ручную правку
админа в панели, и о ней надо знать. Поэтому прогон приводит панель к нашему
состоянию и записывает всё найденное.
"""
```

`run` идёт страницами через `SubscriptionRepository.list_for_reconcile(limit, after_id)`, на каждой подписке зовёт `provisioning.reconcile`, записывает `Difference` в `FindingRepository` с действием `fixed` или `skipped`, глушит `RemnawaveUnavailable` с записью в журнал процесса и продолжает: один недоступный пользователь не должен останавливать прогон.

- [ ] **Шаг 5: Добавить задачу воркера**

В `tasks.py` по образцу `expire_subscriptions`: своя сессия, свой клиент панели, оба закрываются в `finally`. Расписание собирается из `RECONCILE_INTERVAL_HOURS`:

```python
@broker.task(schedule=[{"cron": f"17 */{get_settings().reconcile_interval_hours} * * *"}])
async def reconcile_panel() -> dict[str, int]:
```

Минута 17, а не 0: сверка не должна стартовать одновременно с ежечасным истечением — два прогона, дёргающих панель, дают всплеск запросов на ровном месте.

`run_id` — новый `uuid4()` на каждый прогон, передаётся снаружи сервиса, чтобы тест мог его задать.

- [ ] **Шаг 6: Запустить тесты**

Запуск: `uv run pytest backend/core/tests/test_reconciliation.py backend/core/tests/test_provisioning.py backend/worker -q`
Ожидание: PASS, включая наборы этапа 2a.

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core backend/worker
git commit -m "feat: сверка с панелью по расписанию и отчёт о расхождениях"
```

---

### Задача 11: Типы, хуки и словари фронтенда

**Файлы:**
- Изменить (перегенерацией): `frontend/packages/core/src/api/openapi.json`, `frontend/packages/core/src/api/schema.d.ts`
- Создать: `frontend/packages/core/src/subscription/hooks.tsx`
- Создать: `frontend/packages/core/src/subscription/format.ts`
- Создать: `frontend/packages/core/src/subscription/format.test.ts`
- Изменить: `frontend/packages/core/src/index.ts`
- Изменить: `frontend/packages/core/src/i18n/ru.ts`, `frontend/packages/core/src/i18n/en.ts`

**Интерфейсы:**
- Отдаёт: `usePlans`, `useSubscription`, `useActivateTrial`, `useDevices`, `useUnlinkDevice`, `useTraffic`, `formatBytes`, `formatDate`; ключи словарей с префиксами `plans.*`, `subscription.*`, `devices.*`, `traffic.*`.

- [ ] **Шаг 1: Перегенерировать типы**

```bash
uv run export-openapi
pnpm --filter @repibot/core gen:api
```

Проверка: `uv run verify-generated` — «Сгенерированные файлы актуальны».

- [ ] **Шаг 2: Написать падающий тест форматирования**

```typescript
// frontend/packages/core/src/subscription/format.test.ts
import { describe, expect, it } from 'vitest'

import { formatBytes } from './format'

describe('formatBytes', () => {
  it('показывает безлимит отдельным случаем', () => {
    // Ноль в панели означает «без ограничения», а не «нисколько».
    expect(formatBytes(0, 'ru', { zeroIsUnlimited: true })).toBe('∞')
  })

  it('округляет до одного знака и не пишет дробь у байт', () => {
    expect(formatBytes(512, 'ru')).toBe('512 Б')
    expect(formatBytes(1536, 'ru')).toBe('1,5 КБ')
    expect(formatBytes(1_073_741_824, 'ru')).toBe('1 ГБ')
  })

  it('переводит единицы', () => {
    expect(formatBytes(1536, 'en')).toBe('1.5 KB')
  })
})
```

- [ ] **Шаг 3: Запустить тест и убедиться, что он падает**

Запуск: `cd frontend && pnpm --filter @repibot/core test`
Ожидание: FAIL, модуль `./format` не найден.

- [ ] **Шаг 4: Написать форматирование**

Двоичные приставки (1024), локаль берётся из языка, дробная часть — один знак и только там, где она осмысленна. `Intl.NumberFormat` даёт правильный разделитель для обоих языков без своей таблицы.

- [ ] **Шаг 5: Написать хуки**

По образцу `auth/hooks.tsx`: `useQuery` для чтения, `useMutation` для действий, `queryKey` — `['plans']`, `['subscription']`, `['devices']`, `['traffic']`.

```tsx
export function useSubscription() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['subscription'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/subscription')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/subscription')
      return data
    },
    // Пока доступ выдаётся, состояние меняется само: экран должен догнать
    // его без перезагрузки страницы.
    refetchInterval: (query) =>
      query.state.data?.subscription?.status === 'pending_provision' ? 3000 : false,
  })
}

export function useActivateTrial(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/me/subscription/trial')
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: (data) => queries.setQueryData(['subscription'], data),
  })
}

export function useUnlinkDevice(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (hwid: string) => {
      const { error } = await api.POST('/api/me/devices/unlink', { body: { hwid } })
      if (error) throw new Error(messageFrom(error, language))
    },
    onSuccess: () => queries.invalidateQueries({ queryKey: ['devices'] }),
  })
}
```

`messageFrom` и `errorMessageKey` живут в `auth/hooks.tsx` — вынести их в `errors.ts` внутри пакета и импортировать в оба модуля, а не копировать. В карту кодов добавить `panel_unavailable`, `device_not_found`, `subscription_missing`, `trial_already_used`, `trial_requires_telegram`, `trial_disabled`, `subscription_exists`.

- [ ] **Шаг 6: Дописать словари**

В `ru.ts` и `en.ts` — одинаковый набор ключей, иначе тест `i18n.test.ts` покраснеет:

```
plans.title, plans.empty, plans.per_days, plans.traffic, plans.devices,
plans.price_rub, plans.price_stars, plans.trial_badge
subscription.title, subscription.none, subscription.status.trial,
subscription.status.active, subscription.status.expired,
subscription.status.disabled, subscription.status.pending_provision,
subscription.pending_hint, subscription.expires_at, subscription.link,
subscription.copy, subscription.copied, subscription.qr, subscription.trial_cta
devices.title, devices.empty, devices.limit, devices.unlink,
devices.unlink_confirm, devices.unknown_platform
traffic.title, traffic.used, traffic.unlimited, traffic.last_days
error.panel_unavailable, error.device_not_found, error.subscription_missing,
error.trial_already_used, error.trial_requires_telegram, error.trial_disabled,
error.subscription_exists
```

- [ ] **Шаг 7: Экспортировать из пакета и проверить**

Дописать `index.ts`. Запуск: `cd frontend && pnpm --filter @repibot/core test && pnpm typecheck && pnpm lint`
Ожидание: зелено.

- [ ] **Шаг 8: Коммит**

```bash
git add frontend/packages/core
git commit -m "feat: хуки подписки, устройств и трафика в общем пакете"
```

---

### Задача 12: Витрина тарифов в вебе

**Файлы:**
- Создать: `frontend/apps/web/src/app/plans/page.tsx`
- Создать: `frontend/apps/web/src/components/plan-card.tsx`
- Тест: `frontend/apps/web/src/app/plans/page.test.tsx`

**Перед написанием кода прочитать руководство Next.js 16** в `node_modules/next/dist/docs/` — требование `frontend/apps/web/AGENTS.md`.

**Интерфейсы:**
- Потребляет: `usePlans`, `formatBytes`, словари (задача 11).
- Отдаёт: переиспользуемый компонент `PlanCard` для карточки тарифа.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
// frontend/apps/web/src/app/plans/page.test.tsx
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import Page from './page'

describe('витрина тарифов', () => {
  it('показывает цену, срок и лимиты каждого тарифа', async () => {
    renderWithProviders(<Page />, {
      handlers: {
        '/api/plans': [
          {
            id: 1,
            code: 'month',
            name: { ru: 'Месяц', en: 'Month' },
            description: null,
            duration_days: 30,
            price_rub: '299.00',
            price_stars: 199,
            traffic_limit_bytes: 0,
            hwid_device_limit: 3,
            is_trial: false,
          },
        ],
      },
    })

    expect(await screen.findByText('Месяц')).toBeVisible()
    expect(screen.getByText(/299/)).toBeVisible()
    // Ноль означает безлимит, а не «нисколько трафика».
    expect(screen.getByText('∞')).toBeVisible()
  })

  it('объясняет пустую витрину, а не показывает пустоту', async () => {
    renderWithProviders(<Page />, { handlers: { '/api/plans': [] } })
    expect(await screen.findByText(/тариф/i)).toBeVisible()
  })
})
```

Хелпер `renderWithProviders` уже есть в `src/test/providers.tsx` — способ подмены ответов API взять оттуда, а не изобретать свой.

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `cd frontend && pnpm --filter web test`
Ожидание: FAIL, страница не найдена.

- [ ] **Шаг 3: Написать карточку тарифа и страницу**

Витрина открыта без входа — гейт не нужен. Пустой список объясняется текстом через `EmptyState` из `packages/ui`, а не остаётся пустым экраном. Триальный тариф помечается значком и ценой не показывается.

Цвета, отступы и типографика — только токены `packages/ui`.

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `cd frontend && pnpm --filter web test`
Ожидание: PASS

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/apps/web
git commit -m "feat: витрина тарифов в вебе"
```

---

### Задача 13: Подписка и устройства в кабинете

**Файлы:**
- Создать: `frontend/apps/web/src/app/account/subscription/page.tsx`
- Создать: `frontend/apps/web/src/components/subscription-card.tsx`
- Создать: `frontend/apps/web/src/components/device-list.tsx`
- Создать: `frontend/apps/web/src/components/traffic-bar.tsx`
- Изменить: `frontend/apps/web/src/components/account-shell.tsx`
- Тест: `frontend/apps/web/src/app/account/subscription/page.test.tsx`

**Перед написанием кода прочитать руководство Next.js 16** в `node_modules/next/dist/docs/`.

**Интерфейсы:**
- Потребляет: `useSubscription`, `useActivateTrial`, `useDevices`, `useUnlinkDevice`, `useTraffic`, `formatBytes` (задача 11); специализированную `SubscriptionCard`.
- `PlanCard` из задачи 12 здесь намеренно не используется: текущий API подписки не содержит достоверного immutable snapshot цены, описания и полного срока тарифа. Подставлять текущий каталог или выдуманные значения нельзя — они могут не совпасть с условиями уже купленной подписки.
- Зависимость `qrcode` уже установлена ведущим.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
// frontend/apps/web/src/app/account/subscription/page.test.tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import Page from './page'

const ACTIVE = {
  subscription: {
    plan_code: 'month',
    plan_name: { ru: 'Месяц', en: 'Month' },
    status: 'active',
    started_at: '2026-08-06T12:00:00Z',
    expires_at: '2026-09-05T12:00:00Z',
    subscription_url: 'https://panel.example.org/sub/abc',
    traffic_limit_bytes: 0,
    hwid_device_limit: 3,
  },
  trial_available: false,
}

describe('подписка в кабинете', () => {
  it('показывает состояние, дату и ссылку подключения', async () => {
    renderWithProviders(<Page />, { handlers: { '/api/me/subscription': ACTIVE } })
    expect(await screen.findByText('Месяц')).toBeVisible()
    expect(screen.getByRole('button', { name: /скопировать/i })).toBeVisible()
  })

  it('объясняет ожидание вместо пустого экрана', async () => {
    renderWithProviders(<Page />, {
      handlers: {
        '/api/me/subscription': {
          subscription: { ...ACTIVE.subscription, status: 'pending_provision', subscription_url: null },
          trial_available: false,
        },
      },
    })
    // Пустая карточка без объяснения читается как поломка.
    expect(await screen.findByText(/выдаём доступ/i)).toBeVisible()
  })

  it('предлагает триал, пока он доступен', async () => {
    renderWithProviders(<Page />, {
      handlers: { '/api/me/subscription': { subscription: null, trial_available: true } },
    })
    expect(await screen.findByRole('button', { name: /попробовать/i })).toBeVisible()
  })

  it('не роняет экран, когда панель недоступна', async () => {
    renderWithProviders(<Page />, {
      handlers: {
        '/api/me/subscription': ACTIVE,
        '/api/me/devices': { status: 503, body: { error: { code: 'panel_unavailable' } } },
      },
    })
    // Данные о подписке лежат у нас, и терять весь экран из-за чужого отказа нечестно.
    expect(await screen.findByText('Месяц')).toBeVisible()
    expect(await screen.findByText(/недоступн/i)).toBeVisible()
  })

  it('спрашивает подтверждение перед отвязкой устройства', async () => {
    renderWithProviders(<Page />, {
      handlers: {
        '/api/me/subscription': ACTIVE,
        '/api/me/devices': {
          devices: [
            {
              hwid: 'hwid-1',
              platform: 'iOS',
              device_model: 'iPhone 15',
              os_version: '18.0',
              created_at: '2026-08-06T12:00:00Z',
            },
          ],
          limit: 3,
          used: 1,
        },
      },
    })

    await userEvent.click(await screen.findByRole('button', { name: /отвязать/i }))
    expect(await screen.findByRole('dialog')).toBeVisible()
  })
})
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `cd frontend && pnpm --filter web test`
Ожидание: FAIL, страница не найдена.

- [ ] **Шаг 3: Написать экран**

Состав карточки: название тарифа, состояние, дата окончания, ссылка подключения с кнопкой копирования и QR (`qrcode` отдаёт SVG строкой, вставляется как разметка, без внешних запросов), полоса трафика, список устройств.

Отдельные состояния, каждое со своим текстом: подписки нет и триал доступен; подписки нет и триал недоступен; `pending_provision`; активна; истекла; отключена админом.

Блоки устройств и трафика падают независимо: их отказ показывается внутри блока, карточка подписки остаётся на месте.

Отвязка устройства — через `Dialog` из `packages/ui` с подтверждением: случайное нажатие обрывает человеку доступ на том устройстве, с которого он, возможно, и смотрит.

В `account-shell.tsx` добавить пункт навигации `/account/subscription` со словарным ключом `subscription.title`.

- [ ] **Шаг 4: Запустить тест и убедиться, что он проходит**

Запуск: `cd frontend && pnpm --filter web test && pnpm --filter web typecheck`
Ожидание: PASS

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/apps/web
git commit -m "feat: подписка, трафик и устройства в веб-кабинете"
```

---

### Задача 14: Подписка и устройства в MiniApp

**Файлы:**
- Создать: `frontend/apps/miniapp/src/routes/subscription.tsx`
- Создать: `frontend/apps/miniapp/src/routes/devices.tsx`
- Изменить: `frontend/apps/miniapp/src/router.tsx`
- Изменить: `frontend/apps/miniapp/src/routes/root.tsx`
- Тест: `frontend/apps/miniapp/src/routes/subscription.test.tsx`, `frontend/apps/miniapp/src/routes/devices.test.tsx`

**Интерфейсы:**
- Потребляет: те же хуки из `@repibot/core`, что и веб. Отличается только оболочка.

- [ ] **Шаг 1: Написать падающие тесты**

```tsx
// frontend/apps/miniapp/src/routes/subscription.test.tsx
import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderRoute } from '../test-utils'
import { Subscription } from './subscription'

const ACTIVE = {
  subscription: {
    plan_code: 'month',
    plan_name: { ru: 'Месяц', en: 'Month' },
    status: 'active',
    started_at: '2026-08-06T12:00:00Z',
    expires_at: '2026-09-05T12:00:00Z',
    subscription_url: 'https://panel.example.org/sub/abc',
    traffic_limit_bytes: 0,
    hwid_device_limit: 3,
  },
  trial_available: false,
}

describe('подписка в MiniApp', () => {
  it('показывает тариф, срок и ссылку подключения', async () => {
    renderRoute(<Subscription />, { handlers: { '/api/me/subscription': ACTIVE } })
    expect(await screen.findByText('Месяц')).toBeVisible()
    expect(screen.getByRole('button', { name: /скопировать/i })).toBeVisible()
  })

  it('объясняет ожидание выдачи, а не показывает пустоту', async () => {
    renderRoute(<Subscription />, {
      handlers: {
        '/api/me/subscription': {
          subscription: {
            ...ACTIVE.subscription,
            status: 'pending_provision',
            subscription_url: null,
          },
          trial_available: false,
        },
      },
    })
    expect(await screen.findByText(/выдаём доступ/i)).toBeVisible()
  })

  it('предлагает триал, пока он доступен', async () => {
    renderRoute(<Subscription />, {
      handlers: { '/api/me/subscription': { subscription: null, trial_available: true } },
    })
    expect(await screen.findByRole('button', { name: /попробовать/i })).toBeVisible()
  })
})
```

```tsx
// frontend/apps/miniapp/src/routes/devices.test.tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { renderRoute } from '../test-utils'
import { Devices } from './devices'

const ONE_DEVICE = {
  devices: [
    {
      hwid: 'hwid-1',
      platform: 'iOS',
      device_model: 'iPhone 15',
      os_version: '18.0',
      created_at: '2026-08-06T12:00:00Z',
    },
  ],
  limit: 3,
  used: 1,
}

describe('устройства в MiniApp', () => {
  it('показывает устройство и занятое место в лимите', async () => {
    renderRoute(<Devices />, { handlers: { '/api/me/devices': ONE_DEVICE } })
    expect(await screen.findByText('iPhone 15')).toBeVisible()
    expect(screen.getByText(/1.*3/)).toBeVisible()
  })

  it('спрашивает подтверждение перед отвязкой', async () => {
    // Случайное нажатие обрывает доступ на устройстве, с которого человек,
    // возможно, и смотрит этот экран.
    renderRoute(<Devices />, { handlers: { '/api/me/devices': ONE_DEVICE } })
    await userEvent.click(await screen.findByRole('button', { name: /отвязать/i }))
    expect(await screen.findByRole('dialog')).toBeVisible()
  })

  it('объясняет пустой список', async () => {
    renderRoute(<Devices />, {
      handlers: { '/api/me/devices': { devices: [], limit: 3, used: 0 } },
    })
    expect(await screen.findByText(/пока нет/i)).toBeVisible()
  })
})
```

Имя хелпера и способ подмены ответов взять из `src/test-utils.tsx` — если он называется иначе, чем `renderRoute`, использовать существующее имя, а не заводить своё.

- [ ] **Шаг 2: Запустить тесты и убедиться, что они падают**

Запуск: `cd frontend && pnpm --filter miniapp test`
Ожидание: FAIL, маршруты не найдены.

- [ ] **Шаг 3: Написать экраны и маршруты**

Два экрана: «Подписка» и «Устройства». Навигация — рядом с существующими пунктами в `root.tsx`.

Ссылка подключения в MiniApp копируется той же кнопкой; QR не показывается — приложение и так открыто на телефоне, сканировать нечем и незачем.

- [ ] **Шаг 4: Запустить тесты**

Запуск: `cd frontend && pnpm --filter miniapp test && pnpm --filter miniapp typecheck`
Ожидание: PASS

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/apps/miniapp
git commit -m "feat: подписка и устройства в MiniApp"
```

---

### Задача 15: Панель-заглушка для сквозных тестов

**Файлы:**
- Создать: `backend/core/src/repibot_core/testing/panel_server.py`
- Изменить: `frontend/apps/web/e2e/compose.e2e.yml`
- Изменить: `frontend/apps/web/e2e/stack.env`
- Создать: `frontend/apps/web/e2e/seed.ts`
- Тест: `backend/core/tests/test_panel_server.py`

**Зачем.** Сейчас в сквозном стеке `REMNAWAVE_BASE_URL=http://remnawave.invalid`, то есть панели нет вовсе. Проверить подписку, устройства и трафик через браузер при этом нечем. Заглушка `FakePanel` уже описывает поведение 3.2.1 — не хватает только HTTP-обёртки вокруг неё, чтобы та же логика работала не только внутри процесса тестов.

**Интерфейсы:**
- Отдаёт: ASGI-приложение `panel_app` поверх той же `FakePanel`, запускаемое `uvicorn repibot_core.testing.panel_server:panel_app`; функция `seed(...)` в `seed.ts` для наполнения базы сквозного стека.

- [ ] **Шаг 1: Написать падающий тест**

```python
# backend/core/tests/test_panel_server.py
"""HTTP-обёртка вокруг заглушки панели: та же логика, но по сети."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from repibot_core.integrations.remnawave.client import RemnawaveClient
from repibot_core.integrations.remnawave.types import CreateUserBody
from repibot_core.integrations.remnawave.users import PanelUsers
from repibot_core.testing.panel_server import panel_app


async def test_created_user_is_readable_over_http() -> None:
    transport = httpx.ASGITransport(app=panel_app)
    client = RemnawaveClient(base_url="http://panel.test", token="t", transport=transport)
    users = PanelUsers(client)

    created = await users.create(
        CreateUserBody(username="rp_1", expireAt=datetime(2026, 9, 6, 12, tzinfo=UTC))
    )
    found = await users.resolve(username="rp_1")

    assert found is not None
    assert found.id == created.id
```

- [ ] **Шаг 2: Запустить тест и убедиться, что он падает**

Запуск: `uv run pytest backend/core/tests/test_panel_server.py -q`
Ожидание: FAIL, `ModuleNotFoundError: repibot_core.testing.panel_server`

- [ ] **Шаг 3: Написать сервер**

Тонкое приложение Starlette: один обработчик на все пути, который передаёт запрос в `FakePanel._handle` и возвращает его ответ. Состояние живёт в памяти процесса — контейнер поднимается на прогон и умирает вместе с ним.

Отдельный маршрут `POST /__seed/user` заводит пользователя, устройство и трафик: сквозному тесту нужно подготовить панель до того, как браузер откроет кабинет.

- [ ] **Шаг 4: Подключить к сквозному стеку**

В `compose.e2e.yml` добавить сервис `remnawave-fake` на образе backend с командой `uvicorn repibot_core.testing.panel_server:panel_app --host 0.0.0.0 --port 3000`, в `stack.env` заменить:

```
REMNAWAVE_BASE_URL=http://remnawave-fake:3000
REMNAWAVE_WEBHOOK_SECRET=e2e-remnawave-webhook-secret
ADMIN_TELEGRAM_IDS=
```

- [ ] **Шаг 5: Написать посев данных**

`seed.ts` наполняет базу сквозного стека через `docker compose exec -T postgres psql`: тариф, триальный тариф. Это тестовые данные, а не проверяемое поведение, поэтому идут в обход API — иначе понадобился бы вход админа через Telegram, которого в браузере не изобразить.

- [ ] **Шаг 6: Запустить тесты**

Запуск: `uv run pytest backend/core/tests/test_panel_server.py -q`
Ожидание: PASS

- [ ] **Шаг 7: Коммит**

```bash
git add backend/core frontend/apps/web/e2e
git commit -m "test: панель-заглушка по HTTP для сквозного стека"
```

---

### Задача 16: Сквозной сценарий и документация

**Файлы:**
- Создать: `frontend/apps/web/e2e/subscription.spec.ts`
- Изменить: `docs/superpowers/plans/2026-08-06-subscriptions-devices.md` (раздел «Состояние выполнения»)
- Изменить: `README.md`
- Изменить: `docs/deployment.md`

- [ ] **Шаг 1: Написать сквозной сценарий**

```typescript
// frontend/apps/web/e2e/subscription.spec.ts
import { expect, test } from '@playwright/test'

import { WEB_URL } from './stack'

test('витрина показывает засеянные тарифы', async ({ page }) => {
  await page.goto(`${WEB_URL}/plans`)
  await expect(page.getByText('Месяц')).toBeVisible()
})

test('кабинет объясняет отсутствие подписки', async ({ page }) => {
  // Регистрация по почте — тот же путь, что в auth.spec.ts.
  await registerAndSignIn(page)
  await page.goto(`${WEB_URL}/account/subscription`)
  await expect(page.getByText(/подписки нет/i)).toBeVisible()
})
```

Полный сценарий с активной подпиской, устройствами и отвязкой: подписка и `remnawave_id` пользователя засеваются через `seed.ts`, устройство — через `POST /__seed/user` панели-заглушки, после чего браузер открывает кабинет, видит ссылку подключения, список из одного устройства, отвязывает его с подтверждением и видит пустой список. Триал через браузер не проверяется: он требует привязанного Telegram, которого в Playwright не изобразить.

- [ ] **Шаг 2: Запустить сквозной набор**

Запуск: `cd frontend/apps/web && pnpm exec playwright test`
Ожидание: зелено. Набор поднимает свой стек в отдельном проекте compose и не трогает стек разработчика.

- [ ] **Шаг 3: Прогнать полную проверку**

Запуск: `uv run check`
Ожидание: все восемь проверок зелёные.

- [ ] **Шаг 4: Дописать документацию**

В `docs/deployment.md` — раздел о настройке вебхуков панели: где взять секрет и имя заголовка, какой адрес прописать (`https://ваш-домен/webhook/remnawave`), какие события включить. В `README.md` — состояние: подпроект 2 завершён целиком, перечислить, что появилось. В разделе «Состояние выполнения» этого плана — таблица волн и список правок, найденных при сборке, по образцу плана 2a.

- [ ] **Шаг 5: Проверка на живой панели**

Против настоящей Remnawave 3.2.1, не против заглушки:

1. Включить вебхуки в настройках панели на `https://ваш-домен/webhook/remnawave`, перенести секрет и имя заголовка в `.env`.
2. Отозвать подписку пользователя кнопкой в панели. Ожидается: событие принято (`docker compose logs api | grep webhook`), задача примирения выполнена, панель вернулась к нашему состоянию.
3. Подключиться клиентом и убедиться, что устройство появилось в кабинете, а `platform` и модель заполнены.
4. Отвязать устройство из кабинета и убедиться, что оно исчезло и в панели.
5. Посмотреть трафик после нескольких минут использования — цифра сверху и сумма по дням не должны расходиться.
6. Изменить в панели лимит устройств руками и дождаться сверки: панель возвращается к нашему значению, а в `reconciliation_findings` появляется запись.

Найденное записать в раздел «Состояние выполнения»: заглушка повторяет форму ответов, но не поведение живой панели, и расхождения здесь дороже всего остального в этапе.

- [ ] **Шаг 6: Коммит**

```bash
git add frontend/apps/web/e2e docs README.md
git commit -m "test: сквозной сценарий подписки и устройств"
```

---

## После этого этапа

Подпроект 2 закрыт целиком. Дальше — подпроект 3 «Деньги»: YooKassa, Telegram Stars, промокоды, подарочные ваучеры, рефералы и выплаты. Всё начисление дней там уже готово: финализация платежа зовёт `SubscriptionService.grant_days`, а выдачу доступа делает то же примирение, что и сейчас.
