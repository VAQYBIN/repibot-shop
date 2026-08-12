# Сводка админки — план реализации

> **Для исполнителей:** задачи выполняются по одной, каждая заканчивается зелёными тестами. Шаги отмечены галочками (`- [ ]`).

**Цель:** заменить заглушку `/admin` плитками с числами за выбранный период.

**Устройство:** считает отдельный сервис ядра по нашей базе, в панель не ходит. Деньги и оплаты берутся из заказов одним агрегатом с группировкой по назначению; активные подписки и обращения без ответа — два счётчика состояния на сейчас.

**Основание:** `docs/superpowers/specs/2026-08-12-admin-console-design.md`, раздел 3.

**Стек:** Python 3.13, SQLAlchemy 2 async, FastAPI, pytest; React 19, Next.js 16, TanStack Query, Vitest.

**Предшествует:** план каркаса (`2026-08-12-admin-shell.md`).

## Общие ограничения

- Комментарии и строки документации по-русски, объясняют **почему**.
- TDD: тест пишется первым и обязан упасть по названной причине.
- mypy strict, ruff line-length 100, окончания строк LF.
- Тесты — против настоящего Postgres, `pytestmark = pytest.mark.docker`, фикстура `db_session` из корневого `conftest.py`.
- Админка живёт без переводов — русский прямо в разметке.
- **Агент не выполняет команд git**, не запускает `uv run check` целиком, не форматирует пакет целиком и **не перегенерирует клиент OpenAPI**.
- `# noqa: BLE001` не нужен; `# type: ignore` наугад не ставить.

---

### Задача 1: Подсчёт

**Файлы:**
- Создать: `backend/core/src/repibot_core/services/admin_metrics.py`
- Тест: `backend/core/tests/test_admin_metrics.py`

**Отдаёт:**

```python
class MetricsPeriod(StrEnum):
    today = "today"
    week = "week"
    month = "month"


@dataclass(frozen=True, slots=True)
class Metrics:
    revenue_rub: Decimal
    payments: int
    new_subscriptions: int
    renewals: int
    active_subscriptions: int
    tickets_waiting: int


async def collect_metrics(
    session: AsyncSession, period: MetricsPeriod, *, now: datetime | None = None
) -> Metrics: ...
```

Момент отсчёта принимается параметром: без него тест периода зависел бы от времени суток, в которое его запустили.

- [ ] **Шаг 1: Тест на границы периода**

```python
async def test_orders_outside_the_period_do_not_count(db_session: AsyncSession) -> None:
    """«Сегодня» — это сутки по UTC, как и всё остальное время в системе.

    Заказ, исполненный вчера вечером, не должен попадать в сегодняшнюю
    выручку: по такой цифре нельзя судить, был ли день удачным.
    """
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    await _fulfilled_order(db_session, at=now - timedelta(hours=2), amount="500.00")
    await _fulfilled_order(db_session, at=now - timedelta(hours=20), amount="700.00")

    metrics = await collect_metrics(db_session, MetricsPeriod.today, now=now)

    assert metrics.revenue_rub == Decimal("500.00")
    assert metrics.payments == 1
```

- [ ] **Шаг 2: Тест на неисполненные заказы**

```python
async def test_only_fulfilled_orders_are_money(db_session: AsyncSession) -> None:
    """Ожидающий, просроченный, отменённый и возвращённый заказ деньгами не
    являются: по сумме выставленных счетов нельзя платить зарплату."""
```
Создать по заказу в каждом состоянии, проверить, что выручка считает только `fulfilled`.

- [ ] **Шаг 3: Тест на назначение заказа**

Покупка идёт в «новые подписки», продление — в «продления», подарок — ни туда, ни туда, но в выручку входит.

- [ ] **Шаг 4: Тест на состояние вне периода**

```python
async def test_state_tiles_ignore_the_period(db_session: AsyncSession) -> None:
    """Активные подписки и ждущие ответа обращения — это «сейчас», а не «за
    период»: иначе «активные подписки за сегодня» читается как «появившиеся
    сегодня»."""
```
Проверить, что число одинаково для всех трёх периодов.

- [ ] **Шаг 5: Убедиться, что тесты падают**

```
uv run pytest backend/core/tests/test_admin_metrics.py -q
```
Ожидание: `ModuleNotFoundError: repibot_core.services.admin_metrics`.

- [ ] **Шаг 6: Реализация**

Заказы — один запрос с группировкой по назначению: сумма и число разом, вместо четырёх проходов по одной таблице. Подписки и обращения — по счётчику.

Начало периода: `today` — полночь текущих суток UTC; `week` — семь суток назад от полуночи; `month` — тридцать. Отсчёт от полуночи, а не от «сейчас минус сутки»: сотрудник сравнивает дни, а не скользящие окна.

- [ ] **Шаг 7: Проверка**

```
uv run pytest backend/core/tests/test_admin_metrics.py -q
uv run ruff format <свои файлы>
uv run mypy backend/core/src/repibot_core/services/admin_metrics.py
```

---

### Задача 2: Маршрут сводки

**Файлы:**
- Создать: `backend/api/src/repibot_api/routers/admin/metrics.py`
- Изменить: `backend/api/src/repibot_api/routers/admin/__init__.py` (включить подроутер)
- Изменить: `backend/api/src/repibot_api/schemas.py` (схема ответа)
- Тест: `backend/api/tests/test_admin_metrics.py`

**Маршрут:** `GET /api/admin/metrics?period=today|week|month`, роль `admin`.

Период приходит перечислением, поэтому опечатка в нём — 422 от самого FastAPI, а не пустая сводка.

- [ ] **Шаг 1: Тест на отказ поддержке**

```python
async def test_support_does_not_see_the_money(...) -> None:
    """Сводка — это выручка. Поддержке она не положена по разграничению прав."""
```
Ожидание: 403.

- [ ] **Шаг 2: Тест на ответ администратору**

Все шесть чисел в теле, выручка строкой (десятичное число не должно ехать через float).

- [ ] **Шаг 3: Убедиться, что тесты падают**

```
uv run pytest backend/api/tests/test_admin_metrics.py -q
```
Ожидание: 404.

- [ ] **Шаг 4: Реализация**

- [ ] **Шаг 5: Проверка**

```
uv run pytest backend/api/tests/test_admin_metrics.py -q
uv run ruff format <свои файлы>
uv run mypy backend/api/src
```

---

### Задача 3: Экран сводки

**Файлы:**
- Изменить: `frontend/apps/web/src/app/admin/page.tsx`
- Тест: `frontend/apps/web/src/app/admin/page.test.tsx`

**Потребляет:** `GET /api/admin/metrics` (задача 2). Перенаправление поддержки на `/admin/users` уже сделано планом каркаса — **сохранить его**, заменяется только то, что видит администратор.

- [ ] **Шаг 1: Тест на переключение периода**

```tsx
it('перечитывает числа при смене периода', async () => {
  // Иначе переключатель врёт: подпись сменилась, числа прежние.
})
```

- [ ] **Шаг 2: Тест на подпись состояния**

Плитки «активные подписки» и «ждут ответа» подписаны как состояние на сейчас, а не за период.

- [ ] **Шаг 3: Тест на переход к обращениям**

Плитка «ждут ответа» — ссылка на `/admin/tickets`.

- [ ] **Шаг 4: Убедиться, что тесты падают**

```
cd frontend && pnpm --filter web test -- admin/page
```

- [ ] **Шаг 5: Реализация**

Шесть плиток на `Card`, переключатель периода тремя кнопками. Выручка выводится с разделителями разрядов и знаком рубля. Пока числа не пришли — плитки показывают состояние загрузки, а не нули: ноль выручки и неизвестная выручка выглядят одинаково, но значат разное.

- [ ] **Шаг 6: Тесты проходят**

```
cd frontend && pnpm --filter web test -- admin
cd frontend && pnpm biome check --write apps/web/src/app/admin/page.tsx
cd frontend && pnpm typecheck
```

---

## Проверка после плана

```
uv run pytest backend/core/tests/test_admin_metrics.py backend/api/tests/test_admin_metrics.py -q
cd frontend && pnpm test && pnpm typecheck && pnpm biome check
```
