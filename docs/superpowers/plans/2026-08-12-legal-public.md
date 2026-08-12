# Публичная страница юридического документа

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/legal/<slug>` показывает настоящий документ вместо заглушки, а подвал и лендинг получают способ узнать список документов.

**Architecture:** страница документа собирается на сервере — она входит в карту сайта, и её должно быть видно поисковику. Серверные запросы к API идут по внутреннему адресу отдельным маленьким модулем. Список документов для подвала берётся из браузера обычным хуком TanStack Query.

**Tech Stack:** Next.js 16 (App Router), React 19, TanStack Query, vitest, Playwright.

## Global Constraints

- **Не выполняйте git-команд.** Коммит делает ведущий после проверки задачи.
- **Не запускайте `uv run check` целиком.** Только команды из шагов.
- **Не редактируйте `package.json`, `pnpm-lock.yaml`, `pyproject.toml`, `uv.lock`.**
- Комментарии и строки документации на русском, объясняют «почему», а не «что».
- `// biome-ignore` без сработавшего правила запрещён.
- Строгий TypeScript: `any` и `as` без необходимости не проходят проверку.
- Файлы тестов именуются уникально на весь репозиторий.
- Сначала тест, потом код.
- Используются готовые компоненты `@repibot/ui`; своих кнопок и карточек не заводить.
- Маршруты и контракт API не меняются: этот план только читает то, что уже отдаёт бэкенд.

---

### Task 1: Серверный доступ к API

**Files:**
- Create: `frontend/apps/web/src/lib/server-api.ts`
- Create: `frontend/apps/web/src/lib/server-api.test.ts`
- Modify: `compose.yml`
- Modify: `.env.example`

**Interfaces:**
- Produces:
  - `INTERNAL_API_URL` — переменная окружения контейнера `web`, по умолчанию `http://api:8000`;
  - `fetchFromApi<T>(path: string, options?: { revalidate?: number }): Promise<T | null>` — `null` вместо исключения, если API не ответил или ответил ошибкой.

- [ ] **Step 1: Написать падающий тест**

`frontend/apps/web/src/lib/server-api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchFromApi } from './server-api'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('серверный доступ к API', () => {
  it('ходит по внутреннему адресу, а не по относительному пути', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{ slug: 'terms' }]), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const data = await fetchFromApi<Array<{ slug: string }>>('/api/legal')

    expect(data).toEqual([{ slug: 'terms' }])
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('http://api:8000/api/legal')
  })

  it('берёт адрес из окружения, когда он задан', async () => {
    vi.stubEnv('INTERNAL_API_URL', 'http://127.0.0.1:9000')
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchFromApi('/api/legal')

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('http://127.0.0.1:9000/api/legal')
  })

  it('возвращает null, когда API отвечает ошибкой', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))

    expect(await fetchFromApi('/api/plans')).toBeNull()
  })

  it('возвращает null, когда API недоступен', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))

    expect(await fetchFromApi('/api/plans')).toBeNull()
  })
})
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: FAIL — модуля `server-api` нет.

- [ ] **Step 3: Написать модуль**

`frontend/apps/web/src/lib/server-api.ts`:

```ts
/**
 * Запросы к API из серверных компонентов.
 *
 * В браузере базовый адрес относительный: веб и API стоят за одним nginx.
 * На сервере относительный путь разрешать не от чего, поэтому нужен
 * внутренний адрес контейнера — он и приходит переменной окружения.
 *
 * Ошибка возвращается как `null`, а не бросается: главная и страница
 * документа обязаны открываться, даже когда магазин временно не работает.
 * Пятисотка на витрине из-за недоступного бэкенда — худший из возможных
 * ответов посетителю.
 */

const DEFAULT_API_URL = 'http://api:8000'

/** Цена тарифа меняется раз в месяц, а главную открывают чаще. */
const DEFAULT_REVALIDATE_SECONDS = 60

export async function fetchFromApi<T>(
  path: string,
  options: { revalidate?: number } = {},
): Promise<T | null> {
  const base = process.env.INTERNAL_API_URL ?? DEFAULT_API_URL

  try {
    const response = await fetch(`${base}${path}`, {
      next: { revalidate: options.revalidate ?? DEFAULT_REVALIDATE_SECONDS },
    })
    if (!response.ok) return null
    return (await response.json()) as T
  } catch {
    return null
  }
}
```

- [ ] **Step 4: Объявить переменную окружения**

В `compose.yml` у сервиса `web` добавить к `environment`:

```yaml
      INTERNAL_API_URL: http://api:8000
```

В `.env.example` переменную не добавлять: её значение — имя сервиса внутри compose-сети, а не настройка развёртывания. Если в `.env.example` уже есть похожие внутренние адреса, следуйте тому, что там принято.

- [ ] **Step 5: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: PASS, четыре новых теста.

- [ ] **Step 6: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

---

### Task 2: Хук списка документов

**Files:**
- Create: `frontend/packages/core/src/legal/hooks.tsx`
- Create: `frontend/packages/core/src/legal/hooks.test.tsx`
- Modify: `frontend/packages/core/src/index.ts`

**Interfaces:**
- Produces: `useLegalDocuments(language: Language)` — запрос `GET /api/legal?locale=<language>`, возвращает результат `useQuery` со списком `{ slug, title, published_at }`.

- [ ] **Step 1: Написать падающий тест**

`frontend/packages/core/src/legal/hooks.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useLegalDocuments } from './hooks'

const get = vi.fn()

vi.mock('../auth/hooks', () => ({
  useAuthClient: () => ({ api: { GET: get } }),
}))

function wrapper({ children }: { children: ReactNode }) {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={queries}>{children}</QueryClientProvider>
}

describe('useLegalDocuments', () => {
  it('запрашивает документы для выбранного языка', async () => {
    get.mockResolvedValue({
      data: [{ slug: 'terms', title: 'Условия', published_at: '2026-08-01T00:00:00Z' }],
      error: undefined,
    })

    const { result } = renderHook(() => useLegalDocuments('en'), { wrapper })

    await waitFor(() => expect(result.current.data).toHaveLength(1))
    expect(get).toHaveBeenCalledWith('/api/legal', { params: { query: { locale: 'en' } } })
  })

  it('пустой список — обычный ответ, а не ошибка', async () => {
    get.mockResolvedValue({ data: [], error: undefined })

    const { result } = renderHook(() => useLegalDocuments('ru'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })
})
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/core test`
Expected: FAIL — модуля `./hooks` нет.

- [ ] **Step 3: Написать хук**

`frontend/packages/core/src/legal/hooks.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query'

import { useAuthClient } from '../auth/hooks'
import type { Language } from '../i18n/index'

/**
 * Опубликованные юридические документы.
 *
 * Пустой список — обычное состояние, а не сбой: набор документов заводит
 * администратор, и на свежем развёртывании их просто нет. Поэтому ошибки
 * запроса и пустой ответ должны различаться на стороне вызывающего.
 */
export function useLegalDocuments(language: Language) {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['legal', language],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/legal', {
        params: { query: { locale: language } },
      })
      if (error || !data) throw error ?? new Error('пустой ответ /api/legal')
      return data
    },
    // Документы меняются раз в год: перезапрашивать их при каждом
    // возвращении на вкладку незачем.
    staleTime: 5 * 60 * 1000,
  })
}
```

Сверьте с `frontend/packages/core/src/subscription/hooks.tsx`, как соседние хуки передают параметры запроса, и повторите ту же форму.

- [ ] **Step 4: Экспортировать хук**

В `frontend/packages/core/src/index.ts` добавить `useLegalDocuments` рядом с остальными экспортами, сохраняя алфавитный порядок блока.

- [ ] **Step 5: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/core test`
Expected: PASS, два новых теста.

- [ ] **Step 6: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/core typecheck && pnpm exec biome check .`
Expected: без замечаний.

---

### Task 3: Страница документа

**Files:**
- Modify: `frontend/apps/web/src/app/legal/[slug]/page.tsx`
- Create: `frontend/apps/web/src/app/legal/[slug]/legal-page.test.tsx`

**Interfaces:**
- Consumes: `fetchFromApi` (Task 1).
- Produces: страница `/legal/<slug>` с `<h1>` из заголовка документа и телом из `html`.

**Что показывается:** заголовок первого уровня — `title` документа; ниже подпись «Действует с <дата>»; дальше содержимое. Документа нет — Next-овская страница 404 (`notFound()`), а не карточка «текст появится позже»: ссылку на несуществующий документ никто не должен получить, а если получил — честнее показать 404.

- [ ] **Step 1: Написать падающий тест**

`frontend/apps/web/src/app/legal/[slug]/legal-page.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LegalPage from './page'

const fetchFromApi = vi.fn()
const notFound = vi.fn(() => {
  throw new Error('NEXT_NOT_FOUND')
})

vi.mock('@/lib/server-api', () => ({ fetchFromApi: (path: string) => fetchFromApi(path) }))
vi.mock('next/navigation', () => ({ notFound: () => notFound() }))

beforeEach(() => {
  fetchFromApi.mockReset()
  notFound.mockClear()
})

describe('страница юридического документа', () => {
  it('показывает заголовок и содержимое документа', async () => {
    fetchFromApi.mockResolvedValue({
      slug: 'terms',
      title: 'Пользовательское соглашение',
      html: '<h2>Общие положения</h2>\n<p>Текст.</p>',
      locale: 'ru',
      version: 3,
      published_at: '2026-08-01T00:00:00Z',
    })

    render(await LegalPage({ params: Promise.resolve({ slug: 'terms' }) }))

    expect(
      screen.getByRole('heading', { level: 1, name: 'Пользовательское соглашение' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Общие положения' })).toBeInTheDocument()
  })

  it('отдаёт 404, когда документа нет', async () => {
    fetchFromApi.mockResolvedValue(null)

    await expect(LegalPage({ params: Promise.resolve({ slug: 'nothing' }) })).rejects.toThrow(
      'NEXT_NOT_FOUND',
    )
    expect(notFound).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: FAIL — страница ещё показывает заглушку, заголовка документа в разметке нет.

- [ ] **Step 3: Переписать страницу**

`frontend/apps/web/src/app/legal/[slug]/page.tsx`:

```tsx
import { notFound } from 'next/navigation'

import { fetchFromApi } from '@/lib/server-api'

interface LegalDocument {
  slug: string
  title: string
  html: string
  locale: string
  version: number
  published_at: string
}

/**
 * Юридический документ.
 *
 * Собирается на сервере: страница входит в карту сайта, и её содержимое
 * должно доставаться поисковику, а не появляться после гидратации.
 *
 * HTML вставляется как есть, потому что он собран и очищен на бэкенде.
 * Второй очистки на фронте нет намеренно: два набора правил разъезжаются,
 * и однажды сюда попадёт то, что прошло одну проверку и не прошло другую.
 */
export default async function LegalPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const document = await fetchFromApi<LegalDocument>(`/api/legal/${slug}`)

  if (document === null) notFound()

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-12">
      <h1 className="font-semibold text-h1 text-text">{document.title}</h1>
      <p className="mt-2 text-small text-text-muted">
        Действует с {new Date(document.published_at).toLocaleDateString('ru-RU')}
      </p>
      <div
        className="mt-8 flex flex-col gap-4 text-body text-text-secondary [&_a]:text-text-accent [&_a]:underline [&_h2]:mt-6 [&_h2]:font-semibold [&_h2]:text-h2 [&_h2]:text-text [&_h3]:mt-4 [&_h3]:font-medium [&_h3]:text-h3 [&_h3]:text-text [&_li]:ml-5 [&_li]:list-disc [&_ol_li]:list-decimal"
        // biome-ignore lint/security/noDangerouslySetInnerHtml: HTML собран и очищен на бэкенде, см. repibot_core.content.markdown
        dangerouslySetInnerHTML={{ __html: document.html }}
      />
    </main>
  )
}
```

Подавление `biome-ignore` здесь оставляется только если правило действительно срабатывает. Проверьте это шагом 5: если линтер молчит, строку с подавлением удалите — `RUF100`-подобная проверка Biome ругается на лишние подавления.

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: PASS, два новых теста.

- [ ] **Step 5: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

---

### Task 4: Документ в сквозном контуре

**Files:**
- Modify: `frontend/apps/web/e2e/seed.ts`
- Modify: `frontend/apps/web/e2e/stack.ts`

**Interfaces:**
- Produces: `seedLegalDocuments(): void` — заводит опубликованный документ `terms` на русском, чтобы `/legal/terms` в сквозном обходе перестал быть заглушкой.

**Зачем.** В `frontend/apps/web/e2e/sweep.spec.ts` адрес `/legal/terms` уже перечислен среди публичных экранов. Пока страница была заглушкой, он открывался всегда; после Task 3 без посева он даст 404, и обход упадёт — на настоящей причине, но не там, где её будут искать.

- [ ] **Step 1: Добавить посев**

В `frontend/apps/web/e2e/seed.ts` рядом с остальными функциями посева:

```ts
export function seedLegalDocuments(): void {
  runSql(
    `INSERT INTO legal_documents (slug, locale, title, content, version, published_at)
     VALUES (
       'terms', 'ru', 'Пользовательское соглашение',
       E'## Общие положения\\n\\nТекст соглашения для сквозного обхода.\\n',
       1, now()
     )
     ON CONFLICT (slug, locale, version) DO UPDATE SET
       title = EXCLUDED.title,
       content = EXCLUDED.content,
       published_at = EXCLUDED.published_at,
       withdrawn_at = NULL,
       updated_at = now()`,
  )
}
```

- [ ] **Step 2: Вызвать посев при подъёме контура**

В `frontend/apps/web/e2e/stack.ts` в том месте, где после старта стека вызывается `seed()`, добавить вызов `seedLegalDocuments()` — сразу после него. Импорт добавить к существующему из `./seed`.

- [ ] **Step 3: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

Полный прогон Playwright здесь не запускается: он поднимает свой compose-стек и не укладывается в лимит времени задачи. Обход проверит ведущий после сборки образов.

---

## Готовность плана

После четырёх задач `/legal/<slug>` показывает настоящий текст, страница собирается на сервере, а подвал и лендинг получили оба способа узнать нужное: серверный `fetchFromApi` и клиентский `useLegalDocuments`.
