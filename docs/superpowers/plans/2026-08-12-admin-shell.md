# Каркас админки — план реализации

> **Для исполнителей:** задачи выполняются по одной, каждая заканчивается зелёными тестами. Шаги отмечены галочками (`- [ ]`).

**Цель:** расселить `routers/admin.py` по предметам и дать админке навигацию с разграничением по ролям.

**Устройство:** роутер админки становится пакетом; подроутеры включаются в том же порядке, в каком маршруты шли в одном файле, поэтому схема OpenAPI не меняется ни на строку. Оболочка получает боковое меню, которое показывает только доступные роли разделы, а охрана страницы — список допустимых ролей вместо нынешнего «любой сотрудник».

**Основание:** `docs/superpowers/specs/2026-08-12-admin-console-design.md`, разделы 1 и 5.

**Стек:** Python 3.13, FastAPI, pytest; React 19, Next.js 16, Vitest.

**Этот план идёт первым и в одиночку.** Планы пользователей, сводки и нод добавляют по модулю в тот же пакет; пока расселения нет, они конфликтуют в одном файле на 772 строки.

## Общие ограничения

- Комментарии и строки документации по-русски, объясняют **почему**.
- TDD: тест пишется первым и обязан упасть по названной причине.
- mypy strict, ruff line-length 100, окончания строк LF.
- Админка живёт без переводов — русский прямо в разметке, как в существующих экранах.
- **Агент не выполняет команд git.** Коммиты делает ведущий.
- **Агент не запускает `uv run check` целиком** и не форматирует пакет целиком.
- `# noqa: BLE001` не нужен — правило `BLE` не включено, зато `RUF100` ругается на лишние подавления. `# type: ignore` наугад не ставить: mypy strict считает неиспользуемое подавление ошибкой.

---

### Задача 1: Расселение маршрутов админки

**Файлы:**
- Создать: `backend/api/src/repibot_api/routers/admin/__init__.py`, `catalog.py`, `orders.py`, `broadcasts.py`, `tickets.py`
- Удалить: `backend/api/src/repibot_api/routers/admin.py`
- Изменить: `backend/api/src/repibot_api/main.py` (только строка импорта)

**Отдаёт:** пакет `repibot_api.routers.admin` с прежним `router`, готовый принять модули `users`, `metrics`, `nodes` из соседних планов.

- [ ] **Шаг 1: Снять слепок схемы до переезда**

```
uv run python -c "from repibot_api.main import create_app; import json; print(json.dumps(create_app().openapi(), ensure_ascii=False, sort_keys=True))" > /tmp/openapi-before.json
```
Точное имя фабрики приложения взять из `backend/api/src/repibot_api/main.py`. Файл слепка положить в рабочий каталог, а не в репозиторий.

- [ ] **Шаг 2: Разложить маршруты по предметам**

Границы предметов — по нынешнему файлу:

| Модуль | Что переезжает |
|---|---|
| `catalog.py` | промокоды, тарифы, сквады панели |
| `orders.py` | выдача подписки, отметка возврата, компенсации |
| `broadcasts.py` | рассылки, счёт сегмента |
| `tickets.py` | список обращений, переписка, ответ, закрытие |

Каждый модуль объявляет свой `router = APIRouter()` **без префикса**: префикс `/api/admin` и метка `admin` остаются на общем роутере, иначе адреса поедут.

Помощники переезжают вместе с теми маршрутами, которые ими пользуются. Если помощник нужен двоим — он остаётся общим и живёт в `__init__.py`; таких быть не должно, но проверить нужно, а не предположить.

- [ ] **Шаг 3: Собрать общий роутер**

`routers/admin/__init__.py`:

```python
"""Административные маршруты, разложенные по предметам.

Одним файлом они занимали 772 строки и семь несвязанных тем: тарифы ничего
не знают о рассылках, а рассылки — об обращениях. Пакет разделяет их по
предмету, оставляя адреса на месте.

Порядок включения повторяет прежний порядок маршрутов в файле: схема OpenAPI
перечисляет пути в порядке объявления, и перестановка сдвинула бы
сгенерированный клиент без единого изменения по существу.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from repibot_api.deps import AuthContext, require_role
from repibot_api.routers.admin import broadcasts, catalog, orders, tickets
from repibot_core.db.models import UserRole

router = APIRouter(prefix="/api/admin", tags=["admin"])


class WhoAmIResponse(BaseModel):
    id: int
    role: str


@router.get("/whoami", response_model=WhoAmIResponse)
async def whoami(
    context: Annotated[AuthContext, Depends(require_role(UserRole.admin, UserRole.support))],
) -> WhoAmIResponse:
    """Кто вошёл. Относится ко всей админке, поэтому живёт в её корне."""
    return WhoAmIResponse(id=context.principal.user_id, role=context.principal.role.value)


router.include_router(catalog.router)
router.include_router(orders.router)
router.include_router(broadcasts.router)
router.include_router(tickets.router)
```

- [ ] **Шаг 4: Проверить, что схема не сдвинулась**

```
uv run python -c "<та же команда>" > /tmp/openapi-after.json
diff /tmp/openapi-before.json /tmp/openapi-after.json
```
Ожидание: пустой вывод. Любое расхождение — переезд сделан неверно, а не «допустимое отличие».

- [ ] **Шаг 5: Прогнать тесты админки**

```
uv run pytest backend/api/tests/test_admin_routes.py backend/api/tests/test_admin_plans.py backend/api/tests/test_admin_payments.py backend/api/tests/test_admin_subscription.py backend/api/tests/test_admin_broadcasts.py backend/api/tests/test_admin_tickets.py -q
```
Ожидание: зелено без единой правки тестов. Тесты ходят по адресам, а адреса не менялись; если тест пришлось править — переезд задел поведение.

- [ ] **Шаг 6: Проверка**

```
uv run ruff format backend/api/src/repibot_api/routers/admin
uv run ruff check backend/api/src
uv run mypy backend/api/src
uv run verify-generated
```

---

### Задача 2: Охрана страницы по ролям

**Файлы:**
- Изменить: `frontend/apps/web/src/components/role-guard.tsx`
- Тест: `frontend/apps/web/src/components/role-guard.test.tsx`

**Отдаёт:**

```tsx
<RoleGuard router={router} allow={['admin']}>…</RoleGuard>
```
Свойство `allow` обязательно: раздел без явного списка ролей — это раздел, о правах которого забыли.

- [ ] **Шаг 1: Тест на отказ поддержке**

```tsx
it('уводит поддержку из раздела, открытого только администратору', async () => {
  // Скрытая ссылка защитой не считается, но и показывать чужой раздел на миг
  // нельзя: редирект асинхронный.
})
```
Проверить: разметка не отрисована, вызван `router.replace('/account')`.

- [ ] **Шаг 2: Тест на допуск**

Поддержка проходит в раздел с `allow={['admin', 'support']}`.

- [ ] **Шаг 3: Убедиться, что тесты падают**

```
cd frontend && pnpm --filter web test -- role-guard
```
Ожидание: ошибка типов на неизвестном свойстве `allow` либо отрисовка чужого раздела.

- [ ] **Шаг 4: Реализация**

Константа `ALLOWED` удаляется, список приходит свойством:

```tsx
export interface RoleGuardProps {
  children: ReactNode
  router: AuthGuardRouter
  /** Роли, которым открыт раздел. Без явного списка раздел не защищён. */
  allow: readonly string[]
}
```

- [ ] **Шаг 5: Тесты проходят**

```
cd frontend && pnpm --filter web test -- role-guard
```

---

### Задача 3: Оболочка с меню

**Файлы:**
- Изменить: `frontend/apps/web/src/components/admin-shell.tsx`
- Изменить: `frontend/apps/web/src/app/admin/page.tsx`
- Тест: `frontend/apps/web/src/components/admin-shell.test.tsx`

**Потребляет:** `RoleGuard` со свойством `allow` (задача 2).

- [ ] **Шаг 1: Тест на видимость разделов**

```tsx
it('не показывает поддержке разделы про деньги', async () => {
  // Меню — не защита, но лишняя ссылка ведёт сотрудника на страницу,
  // которая ответит отказом: это не забота, а раздражение.
})
```
Поддержка видит «Пользователи» и «Обращения»; «Сводка», «Платежи», «Рассылки», «Ноды» отсутствуют. Администратор видит все шесть.

- [ ] **Шаг 2: Тест на текущий раздел**

Открытая страница помечена `aria-current="page"` — по образцу `account-shell.tsx`.

- [ ] **Шаг 3: Убедиться, что тесты падают**

```
cd frontend && pnpm --filter web test -- admin-shell
```
Ожидание: меню нет вовсе, ни одной ссылки не найдено.

- [ ] **Шаг 4: Реализация меню**

Список разделов объявляется рядом с оболочкой, каждый со своими ролями:

```tsx
const LINKS = [
  { href: '/admin', label: 'Сводка', roles: ['admin'] },
  { href: '/admin/users', label: 'Пользователи', roles: ['admin', 'support'] },
  { href: '/admin/tickets', label: 'Обращения', roles: ['admin', 'support'] },
  { href: '/admin/payments', label: 'Платежи', roles: ['admin'] },
  { href: '/admin/broadcasts', label: 'Рассылки', roles: ['admin'] },
  { href: '/admin/nodes', label: 'Ноды', roles: ['admin'] },
] as const
```

Разделы «Пользователи» и «Ноды» появятся в соседних планах; ссылки ставятся сразу, потому что меню — предмет этой задачи, а не тех.

Роль берётся тем же способом, что и в охране, — из профиля. Оболочка пускает обе роли (`allow={['admin', 'support']}`), а разграничение внутри делают сами страницы.

Вёрстка: боковая колонка на широком экране, лента сверху на узком. Образец разметки и состояний ссылки — `account-shell.tsx`.

- [ ] **Шаг 5: Поддержку с главной — к пользователям**

`/admin/page.tsx` перестаёт быть обещанием:

```tsx
// Сотруднику поддержки сводка не положена, а пустая главная выглядела бы
// поломкой: он попадает туда, ради чего и открыл админку.
```
Поддержка перенаправляется на `/admin/users`. Администратору страница показывает, что сводка появится, — её содержимое заменит план сводки.

- [ ] **Шаг 6: Тесты проходят**

```
cd frontend && pnpm --filter web test -- admin
cd frontend && pnpm biome check --write apps/web/src/components/admin-shell.tsx apps/web/src/app/admin/page.tsx
cd frontend && pnpm typecheck
```

---

## Проверка после плана

```
uv run pytest backend/api/tests -q
uv run verify-generated
cd frontend && pnpm test && pnpm typecheck && pnpm biome check
```
