# Юридические документы в админке

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** администратор заводит, правит, публикует и снимает юридические документы, в том числе загрузкой текста с Telegra.ph.

**Architecture:** восемь маршрутов под `/api/admin/legal`, все под `require_role(admin)`; публикация и снятие пишутся в `audit_log`. Экран `/admin/legal` — список документов и редактор Markdown с предпросмотром готового HTML и историей версий.

**Tech Stack:** FastAPI, SQLAlchemy, Next.js 16, React 19, TanStack Query, `@repibot/ui`, vitest.

## Global Constraints

- **Не выполняйте git-команд.** Коммит делает ведущий после проверки задачи.
- **Не запускайте `uv run check` целиком.** Только команды из шагов.
- **Не редактируйте `pyproject.toml`, `package.json`, `uv.lock`, `pnpm-lock.yaml`.**
- Комментарии и строки документации на русском, объясняют «почему», а не «что».
- `# noqa` и `// biome-ignore` без сработавшего правила запрещены.
- Строгий mypy и строгий TypeScript.
- Файлы тестов именуются уникально на весь репозиторий.
- Сначала тест, потом код.
- Роль `support` к юридическим текстам не допускается — это проверяется тестом, а не подразумевается.
- В интерфейсе используются готовые компоненты `@repibot/ui`; своих кнопок, полей и таблиц не заводить.

---

### Task 1: Админские маршруты

**Files:**
- Create: `backend/api/src/repibot_api/routers/admin/legal.py`
- Modify: `backend/api/src/repibot_api/routers/admin/__init__.py`
- Modify: `backend/api/src/repibot_api/schemas.py`
- Test: `backend/api/tests/test_admin_legal_routes.py`

**Interfaces:**
- Consumes: `LegalService`, `LegalDocumentView`, `LegalVersionView`, `SLUG_PATTERN` (план `legal-backend`); `TelegraphClient`, `TelegraphError`, `TelegraphPage` (план `legal-import`); `render_markdown`.
- Produces маршруты:

| Метод | Путь | Тело / ответ |
|---|---|---|
| `GET` | `/api/admin/legal` | `list[AdminLegalListItemResponse]` |
| `GET` | `/api/admin/legal/{slug}/{locale}` | `AdminLegalDocumentResponse` |
| `GET` | `/api/admin/legal/{slug}/{locale}/versions` | `list[LegalVersionResponse]` |
| `GET` | `/api/admin/legal/{slug}/{locale}/versions/{version}` | `AdminLegalDocumentResponse` |
| `PUT` | `/api/admin/legal/{slug}/{locale}` | `LegalDraftRequest` → `AdminLegalDocumentResponse` |
| `POST` | `/api/admin/legal/{slug}/{locale}/publish` | → `AdminLegalDocumentResponse` |
| `DELETE` | `/api/admin/legal/{slug}/{locale}` | `204` |
| `POST` | `/api/admin/legal/import` | `LegalImportRequest` → `LegalImportResponse` |

- [ ] **Step 1: Написать падающий тест**

`backend/api/tests/test_admin_legal_routes.py`:

```python
"""Юридические документы через админское API."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.docker

DRAFT = {"title": "Пользовательское соглашение", "content": "## Общие\n\nтекст"}


async def test_support_cannot_touch_legal_documents(
    api_client: AsyncClient, support_headers: dict[str, str]
) -> None:
    """Поддержка не правит условия продажи — то же правило, что с тарифами."""
    whoami = await api_client.get("/api/admin/whoami", headers=support_headers)
    assert whoami.json()["role"] == "support"

    response = await api_client.get("/api/admin/legal", headers=support_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_draft_becomes_published_document(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    saved = await api_client.put(
        "/api/admin/legal/terms/ru", json=DRAFT, headers=admin_headers
    )
    assert saved.status_code == 200
    assert saved.json()["published_at"] is None

    # До публикации документа для публики не существует.
    assert (await api_client.get("/api/legal/terms")).status_code == 404

    published = await api_client.post(
        "/api/admin/legal/terms/ru/publish", headers=admin_headers
    )
    assert published.status_code == 200
    assert published.json()["version"] == 1

    public = await api_client.get("/api/legal/terms")
    assert public.status_code == 200
    assert "<h2>Общие</h2>" in public.json()["html"]


async def test_editing_creates_a_second_version(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await api_client.put("/api/admin/legal/terms/ru", json=DRAFT, headers=admin_headers)
    await api_client.post("/api/admin/legal/terms/ru/publish", headers=admin_headers)

    await api_client.put(
        "/api/admin/legal/terms/ru",
        json={"title": "Пользовательское соглашение", "content": "новая редакция"},
        headers=admin_headers,
    )
    await api_client.post("/api/admin/legal/terms/ru/publish", headers=admin_headers)

    versions = await api_client.get(
        "/api/admin/legal/terms/ru/versions", headers=admin_headers
    )
    assert [item["version"] for item in versions.json()] == [2, 1]

    first = await api_client.get(
        "/api/admin/legal/terms/ru/versions/1", headers=admin_headers
    )
    assert first.json()["content"] == "## Общие\n\nтекст"


async def test_withdrawn_document_disappears_from_the_public_api(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await api_client.put("/api/admin/legal/offer/ru", json=DRAFT, headers=admin_headers)
    await api_client.post("/api/admin/legal/offer/ru/publish", headers=admin_headers)

    removed = await api_client.delete("/api/admin/legal/offer/ru", headers=admin_headers)
    assert removed.status_code == 204

    assert (await api_client.get("/api/legal/offer")).status_code == 404
    # История при этом цела: снятие не стирает текст.
    versions = await api_client.get(
        "/api/admin/legal/offer/ru/versions", headers=admin_headers
    )
    assert len(versions.json()) == 1


async def test_bad_slug_is_rejected(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await api_client.put(
        "/api/admin/legal/Терms!/ru", json=DRAFT, headers=admin_headers
    )

    assert response.status_code in {400, 422}


async def test_import_returns_text_without_saving(
    api_client: AsyncClient, admin_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Импорт кладёт текст в ответ, а не в базу: сохраняет админ, посмотрев его."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "title": "Политика конфиденциальности",
                    "content": [{"tag": "p", "children": ["Текст политики."]}],
                },
            },
        )

    from repibot_core.integrations.telegraph import client as telegraph_client

    monkeypatch.setattr(
        telegraph_client,
        "_transport_for_tests",
        httpx.MockTransport(handler),
        raising=False,
    )

    response = await api_client.post(
        "/api/admin/legal/import",
        json={"url": "https://telegra.ph/Politika-konfidencialnosti-06-01-36"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Политика конфиденциальности"
    assert response.json()["content"] == "Текст политики.\n"
    assert (await api_client.get("/api/admin/legal", headers=admin_headers)).json() == []


async def test_import_rejects_foreign_addresses(
    api_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await api_client.post(
        "/api/admin/legal/import",
        json={"url": "http://api:8000/api/admin/plans"},
        headers=admin_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_source"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `uv run pytest backend/api/tests/test_admin_legal_routes.py -q`
Expected: FAIL — маршрутов нет, 404 вместо 403 и 200.

- [ ] **Step 3: Сделать транспорт клиента подменяемым**

В `backend/core/src/repibot_core/integrations/telegraph/client.py` добавить точку подмены, чтобы тест роутера не ходил в сеть:

```python
# Подменяется в тестах роутера: там клиент создаётся зависимостью, и передать
# ему транспорт аргументом неоткуда. В рабочем коде остаётся None.
_transport_for_tests: httpx.BaseTransport | None = None
```

и в конструкторе:

```python
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS, transport=_transport_for_tests
        )
```

- [ ] **Step 4: Добавить схемы**

В конец `backend/api/src/repibot_api/schemas.py`:

```python
class AdminLegalListItemResponse(BaseModel):
    """Документ в списке админки: что опубликовано и есть ли несохранённая правка."""

    slug: str
    locale: str
    title: str
    published_version: int | None
    published_at: datetime | None
    withdrawn: bool
    has_draft: bool


class AdminLegalDocumentResponse(BaseModel):
    slug: str
    locale: str
    title: str
    content: str
    html: str
    version: int
    published_at: datetime | None


class LegalVersionResponse(BaseModel):
    version: int
    published_at: datetime | None
    withdrawn_at: datetime | None
    created_at: datetime


class LegalDraftRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class LegalImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=500)


class LegalImportResponse(BaseModel):
    title: str
    content: str
```

Если `Field` или `datetime` в файле ещё не импортированы, добавьте импорты к существующим.

- [ ] **Step 5: Написать роутер**

`backend/api/src/repibot_api/routers/admin/legal.py`:

```python
"""Юридические документы: правка, публикация, история.

Роль support сюда не допускается по той же причине, что и к тарифам: условия
продажи — не предмет работы поддержки. Публикация и снятие пишутся в журнал
действий: это ровно те события, о которых потом спрашивают.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from repibot_api.deps import AuthContext, db_session, require_role
from repibot_api.errors import ApiError, api_error_from_service
from repibot_api.schemas import (
    AdminLegalDocumentResponse,
    AdminLegalListItemResponse,
    LegalDraftRequest,
    LegalImportRequest,
    LegalImportResponse,
    LegalVersionResponse,
)
from repibot_core.content.markdown import render_markdown
from repibot_core.db.models import UserRole
from repibot_core.db.repositories.audit import AuditRepository
from repibot_core.integrations.telegraph.client import TelegraphClient, TelegraphError
from repibot_core.services.errors import ServiceError
from repibot_core.services.legal import LegalDocumentView, LegalService

router = APIRouter()

# Ограничения на месте параметров пути: имя документа попадает в адрес, и
# проверять его после того, как оно уже стало частью маршрута, поздно.
SlugPath = Annotated[str, Path(pattern="^[a-z0-9-]{2,64}$")]
LocalePath = Annotated[str, Path(pattern="^(ru|en)$")]

AdminOnly = Annotated[AuthContext, Depends(require_role(UserRole.admin))]


@router.get("/legal", response_model=list[AdminLegalListItemResponse])
async def list_legal(
    session: Annotated[AsyncSession, Depends(db_session)],
    _: AdminOnly,
) -> list[AdminLegalListItemResponse]:
    service = LegalService(session)
    items: list[AdminLegalListItemResponse] = []
    for slug, locale in await service.known_slugs():
        versions = await service.versions(slug, locale)
        published = next((item for item in versions if item.published_at is not None), None)
        current = await service.current(slug, locale)
        items.append(
            AdminLegalListItemResponse(
                slug=slug,
                locale=locale,
                title="" if current is None else current.title,
                published_version=None if published is None else published.version,
                published_at=None if published is None else published.published_at,
                withdrawn=published is not None and published.withdrawn_at is not None,
                has_draft=any(item.published_at is None for item in versions),
            )
        )
    return items


@router.get("/legal/{slug}/{locale}", response_model=AdminLegalDocumentResponse)
async def read_legal(
    slug: SlugPath,
    locale: LocalePath,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: AdminOnly,
) -> AdminLegalDocumentResponse:
    document = await LegalService(session).current(slug, locale)
    if document is None:
        raise ApiError("документ не найден", 404, "not_found")
    return _response(document)


@router.get("/legal/{slug}/{locale}/versions", response_model=list[LegalVersionResponse])
async def list_versions(
    slug: SlugPath,
    locale: LocalePath,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: AdminOnly,
) -> list[LegalVersionResponse]:
    return [
        LegalVersionResponse(
            version=item.version,
            published_at=item.published_at,
            withdrawn_at=item.withdrawn_at,
            created_at=item.created_at,
        )
        for item in await LegalService(session).versions(slug, locale)
    ]


@router.get(
    "/legal/{slug}/{locale}/versions/{version}", response_model=AdminLegalDocumentResponse
)
async def read_version(
    slug: SlugPath,
    locale: LocalePath,
    version: int,
    session: Annotated[AsyncSession, Depends(db_session)],
    _: AdminOnly,
) -> AdminLegalDocumentResponse:
    document = await LegalService(session).version(slug, locale, version)
    if document is None:
        raise ApiError("версия не найдена", 404, "not_found")
    return _response(document)


@router.put("/legal/{slug}/{locale}", response_model=AdminLegalDocumentResponse)
async def save_draft(
    slug: SlugPath,
    locale: LocalePath,
    payload: LegalDraftRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: AdminOnly,
) -> AdminLegalDocumentResponse:
    try:
        document = await LegalService(session).save_draft(
            slug=slug,
            locale=locale,
            title=payload.title,
            content=payload.content,
            author_id=context.principal.user_id,
        )
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return _response(document)


@router.post("/legal/{slug}/{locale}/publish", response_model=AdminLegalDocumentResponse)
async def publish(
    slug: SlugPath,
    locale: LocalePath,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: AdminOnly,
) -> AdminLegalDocumentResponse:
    try:
        document = await LegalService(session).publish(slug=slug, locale=locale)
        await AuditRepository(session).record(
            "legal.publish",
            "legal_document",
            actor_id=context.principal.user_id,
            entity_id=f"{slug}:{locale}",
            after={"version": document.version},
        )
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error
    return _response(document)


@router.delete("/legal/{slug}/{locale}", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw(
    slug: SlugPath,
    locale: LocalePath,
    session: Annotated[AsyncSession, Depends(db_session)],
    context: AdminOnly,
) -> None:
    try:
        await LegalService(session).withdraw(slug=slug, locale=locale)
        await AuditRepository(session).record(
            "legal.withdraw",
            "legal_document",
            actor_id=context.principal.user_id,
            entity_id=f"{slug}:{locale}",
        )
        await session.commit()
    except ServiceError as error:
        raise api_error_from_service(error) from error


@router.post("/legal/import", response_model=LegalImportResponse)
async def import_from_telegraph(
    payload: LegalImportRequest,
    _: AdminOnly,
) -> LegalImportResponse:
    """Забирает текст к себе. Ничего не сохраняет — это делает админ, посмотрев результат."""
    try:
        page = await TelegraphClient().fetch(payload.url)
    except TelegraphError as error:
        status_code = {"invalid_source": 400, "not_found": 404}.get(error.code, 502)
        raise ApiError(str(error), status_code, error.code) from error
    return LegalImportResponse(title=page.title, content=page.content)


def _response(document: LegalDocumentView) -> AdminLegalDocumentResponse:
    return AdminLegalDocumentResponse(
        slug=document.slug,
        locale=document.locale,
        title=document.title,
        content=document.content,
        html=render_markdown(document.content),
        version=document.version,
        published_at=document.published_at,
    )
```

Сверьте, как соседние админские роутеры получают идентификатор вошедшего из `AuthContext`, и повторите этот способ.

- [ ] **Step 6: Подключить роутер**

В `backend/api/src/repibot_api/routers/admin/__init__.py` добавить `legal` в импорт и `router.include_router(legal.router)` **последней строкой**: порядок объявления определяет порядок путей в схеме OpenAPI, поэтому существующие строки не переставляются.

- [ ] **Step 7: Убедиться, что тесты проходят**

Run: `uv run pytest backend/api/tests/test_admin_legal_routes.py -q`
Expected: PASS, 7 тестов.

- [ ] **Step 8: Обновить схему и типы клиента**

Run: `uv run export-openapi && cd frontend && pnpm --filter @repibot/core gen:api`
Затем: `uv run verify-generated`
Expected: без замечаний.

- [ ] **Step 9: Проверить линтеры и типы**

Run: `uv run ruff check backend && uv run ruff format --check backend && uv run mypy backend`
Expected: без замечаний.

---

### Task 2: Экран администратора

**Files:**
- Create: `frontend/apps/web/src/app/admin/legal/page.tsx`
- Create: `frontend/apps/web/src/app/admin/legal/page.test.tsx`
- Modify: `frontend/apps/web/src/components/admin-shell.tsx`

**Interfaces:**
- Consumes: маршруты из Task 1 через типизированный клиент (`api.GET('/api/admin/legal')` и далее).
- Produces: экран `/admin/legal`.

**Устройство экрана.** Слева список документов (slug, локаль, опубликованная версия, отметка о черновике), справа редактор выбранного: поле заголовка, поле Markdown, поле адреса Telegra.ph с кнопкой «Загрузить», кнопки «Сохранить черновик», «Опубликовать», «Снять с публикации», вкладки «Текст» и «Предпросмотр», список версий. Кнопка «Новый документ» открывает диалог с полями slug и локали.

- [ ] **Step 1: Написать падающий тест**

`frontend/apps/web/src/app/admin/legal/page.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import LegalAdminPage from './page'

const documents = [
  {
    slug: 'terms',
    locale: 'ru',
    title: 'Пользовательское соглашение',
    published_version: 1,
    published_at: '2026-08-01T00:00:00Z',
    withdrawn: false,
    has_draft: false,
  },
]

const document = {
  slug: 'terms',
  locale: 'ru',
  title: 'Пользовательское соглашение',
  content: '## Общие\n\nтекст',
  html: '<h2>Общие</h2>\n<p>текст</p>',
  version: 1,
  published_at: '2026-08-01T00:00:00Z',
}

const get = vi.fn()
const put = vi.fn()
const post = vi.fn()

vi.mock('@repibot/core', () => ({
  useAuthClient: () => ({ api: { GET: get, PUT: put, POST: post } }),
  useMe: () => ({ data: { role: 'admin', language: 'ru' } }),
}))

function renderPage() {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queries}>
      <LegalAdminPage />
    </QueryClientProvider>,
  )
}

describe('экран юридических документов', () => {
  it('показывает пустое состояние, когда документов нет', async () => {
    get.mockResolvedValue({ data: [], error: undefined })

    renderPage()

    expect(await screen.findByText(/пока нет/i)).toBeInTheDocument()
  })

  it('открывает документ и показывает предпросмотр', async () => {
    get.mockImplementation((path: string) =>
      path === '/api/admin/legal'
        ? Promise.resolve({ data: documents, error: undefined })
        : Promise.resolve({ data: document, error: undefined }),
    )

    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /Пользовательское соглашение/i }))

    await userEvent.click(await screen.findByRole('tab', { name: /предпросмотр/i }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Общие' })).toBeInTheDocument())
  })

  it('подставляет загруженный с Telegra.ph текст в поля, не сохраняя его', async () => {
    get.mockImplementation((path: string) =>
      path === '/api/admin/legal'
        ? Promise.resolve({ data: documents, error: undefined })
        : Promise.resolve({ data: document, error: undefined }),
    )
    post.mockResolvedValue({
      data: { title: 'Политика', content: 'Текст политики.' },
      error: undefined,
    })

    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /Пользовательское соглашение/i }))

    await userEvent.type(
      await screen.findByLabelText(/ссылка на telegra\.ph/i),
      'https://telegra.ph/Politika-06-01-36',
    )
    await userEvent.click(screen.getByRole('button', { name: /загрузить/i }))

    await waitFor(() =>
      expect(screen.getByLabelText(/заголовок/i)).toHaveValue('Политика'),
    )
    expect(put).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: FAIL — модуля `./page` нет.

- [ ] **Step 3: Написать экран**

`frontend/apps/web/src/app/admin/legal/page.tsx` — клиентский компонент (`'use client'`), собранный из `AdminPage`, `Card`, `Button`, `FormField`, `Input`, `Textarea`, `Select`, `Tabs`, `Table`, `Alert`, `Spinner`, `EmptyState`, `Dialog` и `Badge`.

Требования к поведению, каждое из которых видно в тестах или следует из спецификации:

- Список документов приходит из `GET /api/admin/legal`. Пусто — `EmptyState` с текстом «Документов пока нет» и кнопкой «Новый документ».
- Выбор документа грузит `GET /api/admin/legal/{slug}/{locale}` и заполняет поля заголовка и текста.
- Вкладки: «Текст» — `Textarea` с Markdown; «Предпросмотр» — готовый `html` из ответа, вставленный через `dangerouslySetInnerHTML`. Вставлять можно именно потому, что HTML собран и очищен на бэкенде — своей очистки на фронте нет и не должно быть, иначе появятся два разных набора правил.
- «Загрузить» шлёт `POST /api/admin/legal/import` с адресом и подставляет `title` и `content` в поля. Сохранения при этом не происходит — админ смотрит и решает сам.
- «Сохранить черновик» — `PUT`, «Опубликовать» — `POST …/publish`, «Снять с публикации» — `DELETE` с подтверждением через `Dialog`, потому что действие видно всем посетителям сайта.
- Ошибки показываются `Alert tone="error"` с текстом из ответа; ошибка импорта не затирает набранный текст.
- Список версий — `Table` со столбцами «Версия», «Опубликована», «Снята»; нажатие на строку открывает текст версии.
- Заголовок страницы — «Юридические документы», описание — «Тексты соглашения, политики и оферты. Публикуются сразу после нажатия».

- [ ] **Step 4: Добавить пункт навигации**

В `frontend/apps/web/src/components/admin-shell.tsx` в массив ссылок добавить после «Ноды»:

```tsx
  { href: '/admin/legal', label: 'Документы', roles: ['admin'], icon: DocumentValidationIcon },
```

и импортировать `DocumentValidationIcon` из `@hugeicons/core-free-icons`. Если иконки с таким именем в пакете нет, возьмите ближайшую по смыслу из тех, что есть, и не заводите свою.

- [ ] **Step 5: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: PASS, включая три новых теста.

- [ ] **Step 6: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

---

## Готовность плана

После двух задач документ заводится, правится, публикуется и снимается через админку, а текст можно загрузить с Telegra.ph одной кнопкой. Публичная страница документа и подвал со ссылками — следующий план.
