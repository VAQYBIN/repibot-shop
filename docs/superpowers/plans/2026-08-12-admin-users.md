# Пользователи в админке — план реализации

> **Для исполнителей:** задачи выполняются по одной, каждая заканчивается зелёными тестами. Шаги отмечены галочками (`- [ ]`).

**Цель:** дать поддержке и администратору поиск человека, его карточку целиком и действия над ним — от блокировки до выдачи дней.

**Устройство:** поиск и сборка карточки живут отдельным сервисом ядра, ничего не знающим про HTTP; маршруты только переводят его ответы в схемы. Журнал склеивается на сервере из трёх источников — начислений, заказов и журнала действий, — потому что три ленты, собранные в браузере, дали бы три запроса и разъезжающуюся разбивку.

**Основание:** `docs/superpowers/specs/2026-08-12-admin-console-design.md`, раздел 2.

**Стек:** Python 3.13, SQLAlchemy 2 async, FastAPI, pytest; React 19, Next.js 16, TanStack Query, Vitest.

**Предшествует:** план каркаса (`2026-08-12-admin-shell.md`). Без расселения маршрутов этот план конфликтует с соседними в одном файле.

## Общие ограничения

- Комментарии и строки документации по-русски, объясняют **почему**.
- TDD: тест пишется первым и обязан упасть по названной причине.
- mypy strict, ruff line-length 100, окончания строк LF.
- Тесты ядра и API — против настоящего Postgres, `pytestmark = pytest.mark.docker`, фикстуры `db_session` и `engine` из корневого `conftest.py`.
- Админка живёт без переводов — русский прямо в разметке.
- **Агент не выполняет команд git**, не запускает `uv run check` целиком, не форматирует пакет целиком и **не перегенерирует клиент OpenAPI** — это делает ведущий один раз на волну.
- `# noqa: BLE001` не нужен; `# type: ignore` наугад не ставить.

## Права

Из спецификации, соблюдается на каждом маршруте отдельно:

| Действие | Роли |
|---|---|
| Поиск, карточка, журнал | `support`, `admin` |
| Блокировка, разблокировка, заглушение, снятие заглушения | `support`, `admin` |
| Отвязка устройства, новая ссылка подписки | `support`, `admin` |
| Выдать или снять дни, сменить тариф | `admin` |

---

### Задача 1: Поиск и список

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/admin_users.py`
- Тест: `backend/core/tests/test_admin_users_service.py`

**Отдаёт:**

```python
@dataclass(frozen=True, slots=True)
class UserRow:
    id: int
    name: str | None
    email: str | None
    telegram_id: int | None
    telegram_username: str | None
    plan_name: str | None
    subscription_status: str | None
    expires_at: datetime | None
    banned: bool
    support_muted: bool


async def search_users(
    session: AsyncSession, query: str, *, limit: int, offset: int
) -> list[UserRow]: ...
```

- [ ] **Шаг 1: Тест на разбор строки поиска**

```python
async def test_digits_match_every_numeric_identifier(db_session: AsyncSession) -> None:
    """Гадать по длине нельзя: номер в панели растёт с каждым заведённым
    пользователем и однажды сравняется по длине с номером аккаунта."""
    by_account = await _user(db_session, "search01", telegram_id=700_001, remnawave_id=42)
    by_panel = await _user(db_session, "search02", telegram_id=700_002, remnawave_id=700_001)

    found = await search_users(db_session, "700001", limit=20, offset=0)

    assert {row.id for row in found} == {by_account.id, by_panel.id}
```

Разбор — три правила: строка из одних цифр ищется по номеру аккаунта, Telegram и панели одновременно; строка, начинающаяся с `@`, — имя пользователя Telegram; всё остальное — вхождение по почте и имени.

- [ ] **Шаг 2: Убедиться, что тест падает**

```
uv run pytest backend/core/tests/test_admin_users_service.py -q
```
Ожидание: `ModuleNotFoundError: repibot_core.services.admin_users`.

- [ ] **Шаг 3: Реализация поиска**

Один запрос с присоединением подписки и тарифа: строка списка показывает тариф и срок, а отдельный запрос на каждую строку превратил бы страницу в двадцать запросов.

Пустой запрос отдаёт свежих сверху — список без строки поиска всё равно нужен, чтобы увидеть пришедших сегодня.

- [ ] **Шаг 4: Тесты на остальные правила**

По тесту на каждое: `@username`, почта по вхождению, имя по вхождению, пустая строка (свежие сверху), смещение и предел, человек без подписки (в строке пусто, а не отсутствие строки).

- [ ] **Шаг 5: Проверка**

```
uv run pytest backend/core/tests/test_admin_users_service.py -q
uv run ruff format <свои файлы>
uv run mypy backend/core/src/repibot_core/services/admin_users.py
```

---

### Задача 2: Карточка и журнал

**Файлы:**
- Изменить: `backend/core/src/repibot_core/services/admin_users.py`
- Тест: `backend/core/tests/test_admin_users_service.py`

**Отдаёт:**

```python
@dataclass(frozen=True, slots=True)
class JournalEntry:
    at: datetime
    kind: str          # subscription | payment | staff
    title: str
    detail: str | None
    actor: str | None  # имя или почта автора; None — система


@dataclass(frozen=True, slots=True)
class UserCard:
    row: UserRow
    language: str
    role: str
    created_at: datetime
    email_verified: bool
    referred_by_id: int | None
    subscription_source: str | None
    auto_renew: bool
    subscription_url: str | None
    remnawave_id: int | None


async def user_card(session: AsyncSession, user_id: int) -> UserCard | None: ...
async def user_journal(session: AsyncSession, user_id: int, *, limit: int) -> list[JournalEntry]: ...
```

Устройства в карточку не входят: их отдаёт панель, а не база, и просить их должен маршрут — иначе молчащая панель уронила бы всю карточку.

- [ ] **Шаг 1: Тест на склейку журнала**

```python
async def test_journal_merges_three_sources_by_time(db_session: AsyncSession) -> None:
    """Начисление, оплата и решение персонала — одна история одного человека.
    Порядок обратный: разбирают всегда последнее, а не первое."""
```
Создать по записи в `subscription_events`, `orders` и `audit_log`, проверить порядок и виды.

- [ ] **Шаг 2: Тест на удалённого автора**

```python
async def test_journal_survives_a_deleted_actor(db_session: AsyncSession) -> None:
    """`audit_log.actor_id` гаснет вместе с аккаунтом сотрудника, а запись
    остаётся: журнал не должен терять строку из-за уволенного коллеги."""
```

- [ ] **Шаг 3: Убедиться, что тесты падают**

```
uv run pytest backend/core/tests/test_admin_users_service.py -q -k journal
```

- [ ] **Шаг 4: Реализация**

Три выборки с общим пределом, склейка по времени в памяти. Ограничение берётся с запасом на каждую ленту и режется после склейки: иначе сто платежей вытеснили бы из ленты все начисления.

- [ ] **Шаг 5: Тест карточки**

Полная карточка, человек без подписки, человек без Telegram, несуществующий номер (`None`).

- [ ] **Шаг 6: Проверка**

```
uv run pytest backend/core/tests/test_admin_users_service.py -q
uv run ruff format <свои файлы>
uv run mypy backend/core/src/repibot_core/services/admin_users.py
```

---

### Задача 3: Маршруты пользователей

**Файлы:**
- Создать: `backend/api/src/repibot_api/routers/admin/users.py`
- Изменить: `backend/api/src/repibot_api/routers/admin/__init__.py` (включить подроутер последним)
- Схемы ответов объявляются **в самом модуле маршрута**, а не в общем `schemas.py`: соседние планы наполняют пакет админки одновременно, и общий файл стал бы местом столкновения. Прецедент — `WhoAmIResponse` в корне пакета.
- Изменить: `backend/core/src/repibot_core/integrations/remnawave/users.py` (метод выпуска новой ссылки)
- Тест: `backend/api/tests/test_admin_users.py`

**Маршруты:**

| Метод и адрес | Роли | Что делает |
|---|---|---|
| `GET /api/admin/users` | обе | поиск, `query`, `limit`, `offset` |
| `GET /api/admin/users/{user_id}` | обе | карточка |
| `GET /api/admin/users/{user_id}/journal` | обе | лента событий |
| `GET /api/admin/users/{user_id}/devices` | обе | устройства из панели |
| `DELETE /api/admin/users/{user_id}/devices/{hwid}` | обе | отвязать устройство |
| `POST /api/admin/users/{user_id}/block` | обе | заблокировать |
| `POST /api/admin/users/{user_id}/unblock` | обе | разблокировать |
| `POST /api/admin/users/{user_id}/mute` | обе | закрыть поддержку |
| `POST /api/admin/users/{user_id}/unmute` | обе | открыть поддержку |
| `POST /api/admin/users/{user_id}/subscription/revoke-link` | обе | новая ссылка подписки |

Выдача дней и смена тарифа уже существуют — `POST /api/admin/users/{user_id}/subscription` в модуле `orders`, роль `admin`. Здесь не дублируются.

- [ ] **Шаг 1: Тест на разграничение прав**

```python
async def test_support_cannot_grant_days(...) -> None:
    """Сотрудник, умеющий выдать себе год подписки, — это не поддержка."""
```
И парный: поддержка **может** заблокировать и отвязать устройство.

- [ ] **Шаг 2: Тест на отказ панели**

```python
async def test_a_silent_panel_does_not_break_the_card(...) -> None:
    """Устройства просит отдельный маршрут именно поэтому: карточка обязана
    открыться и тогда, когда панель молчит."""
```
Карточка отвечает 200, устройства — `panel_unavailable` (503).

- [ ] **Шаг 3: Убедиться, что тесты падают**

```
uv run pytest backend/api/tests/test_admin_users.py -q
```
Ожидание: 404 на всех новых адресах.

- [ ] **Шаг 4: Блокировка через готовый сервис**

Блокировка, разблокировка, заглушение и снятие зовут `ModerationService` — тот же, что и команды в теме поддержки. Возвращаемый `bool` превращается в тело ответа `{"changed": true|false}`: интерфейсу нужно отличать «заблокировали» от «уже был заблокирован».

Каждое действие уже пишется в журнал самим сервисом — второй записи здесь делать не нужно.

- [ ] **Шаг 5: Новая ссылка подписки**

В `PanelUsers` добавляется метод, зовущий `/api/users/{panel_id}/actions/revoke`. Ответ панели несёт новый `shortUuid` и адрес подписки; ими перезаписываются `remnawave_short_uuid` и `remnawave_subscription_url` — иначе кабинет продолжит показывать мёртвую ссылку.

Схема ответа панели добавляется в список генерируемых моделей, если её там ещё нет; перегенерацию моделей панели делает ведущий.

- [ ] **Шаг 6: Тесты проходят**

```
uv run pytest backend/api/tests/test_admin_users.py -q
uv run ruff format <свои файлы>
uv run mypy backend/api/src backend/core/src/repibot_core/integrations
```

---

### Задача 4: Экран списка

**Файлы:**
- Создать: `frontend/apps/web/src/app/admin/users/page.tsx`, `page.test.tsx`

**Потребляет:** `GET /api/admin/users` (задача 3), меню админки (план каркаса).

- [ ] **Шаг 1: Тест на поиск**

```tsx
it('ищет по одной строке любым опознавателем', async () => {
  // Сотрудник не знает, что ему дали — почту, ссылку на Telegram или номер:
  // разбираться должен сервер, а не человек.
})
```

- [ ] **Шаг 2: Тест на пустой ответ и на «ещё»**

Пустой ответ — `EmptyState`, а не пустая таблица. Кнопка «ещё» дописывает строки, а не заменяет их.

- [ ] **Шаг 3: Убедиться, что тесты падают**

```
cd frontend && pnpm --filter web test -- admin/users
```

- [ ] **Шаг 4: Реализация**

Строка поиска с задержкой ввода, таблица из строк, отметки ⛔ и 🔇 у ограниченных, ссылка со строки на карточку. Образец обращения к API и разбора отказов — `admin/tickets/page.tsx`.

- [ ] **Шаг 5: Тесты проходят**

```
cd frontend && pnpm --filter web test -- admin/users
cd frontend && pnpm biome check --write apps/web/src/app/admin/users
```

---

### Задача 5: Экран карточки

**Файлы:**
- Создать: `frontend/apps/web/src/app/admin/users/[id]/page.tsx`, `page.test.tsx`

**Потребляет:** карточку, журнал, устройства и действия (задача 3).

- [ ] **Шаг 1: Тест на разграничение кнопок**

```tsx
it('не показывает поддержке кнопки про дни и тариф', async () => {
  // Отказ сервера — последняя линия, а не первая: кнопка, которая всегда
  // отвечает «нельзя», хуже отсутствующей.
})
```

- [ ] **Шаг 2: Тест на подтверждение опасных действий**

Блокировка и новая ссылка подписки спрашивают подтверждение через `Dialog`: обе необратимы для человека по ту сторону — заблокированный теряет вход, а старая ссылка перестаёт работать на всех его устройствах.

- [ ] **Шаг 3: Тест на молчащую панель**

Карточка показана целиком, на месте устройств — сообщение об отказе и кнопка «повторить».

- [ ] **Шаг 4: Убедиться, что тесты падают**

```
cd frontend && pnpm --filter web test -- 'admin/users/\[id\]'
```

- [ ] **Шаг 5: Реализация**

Четыре части из спецификации: кто это, подписка с устройствами, действия, журнал. После любого действия перечитываются карточка и журнал: решение персонала — это событие ленты, и не показать его сразу значит заставить сотрудника обновлять страницу.

- [ ] **Шаг 6: Тесты проходят**

```
cd frontend && pnpm --filter web test -- admin
cd frontend && pnpm biome check --write apps/web/src/app/admin/users
cd frontend && pnpm typecheck
```

---

## Проверка после плана

```
uv run pytest backend/core/tests/test_admin_users_service.py backend/api/tests/test_admin_users.py -q
cd frontend && pnpm test && pnpm typecheck && pnpm biome check
```
