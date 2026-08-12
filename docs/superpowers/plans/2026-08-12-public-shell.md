# Публичная оболочка сайта

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** у публичных страниц появляются общие шапка и подвал, под кнопкой регистрации — согласие с документами, а у сайта — открытая графика и карта сайта.

**Architecture:** маршруты `/`, `/plans` и `/legal/*` переезжают в группу `(public)` с общим макетом — адреса при этом не меняются. Подвал берёт правовые ссылки клиентским хуком и не рисует колонку, когда документов нет. Карта сайта собирается на сервере.

**Tech Stack:** Next.js 16 (App Router, route groups, `MetadataRoute`), React 19, `@repibot/ui`, vitest.

## Global Constraints

- **Не выполняйте git-команд.** Коммит делает ведущий после проверки задачи.
- **Не запускайте `uv run check` целиком.** Только команды из шагов.
- **Не редактируйте `package.json`, `pnpm-lock.yaml`.** Зависимости уже на месте.
- **Ключи переводов уже добавлены ведущим** в `frontend/packages/core/src/i18n/{ru,en}.ts`. Список — в разделе «Ключи» ниже. Если какого-то ключа нет — остановитесь и сообщите, сами файлы словарей не правьте.
- Комментарии и строки документации на русском, объясняют «почему», а не «что».
- `// biome-ignore` без сработавшего правила запрещён.
- Строгий TypeScript.
- Файлы тестов именуются уникально на весь репозиторий.
- Сначала тест, потом код.
- **Адреса страниц не меняются.** Группа `(public)` — скобки в имени каталога, Next не включает её в путь. Если после переноса какой-то адрес изменился — перенос сделан неверно.

## Ключи

Уже лежат в словарях, используйте их, а не строковые литералы:

| Ключ | Русский |
|---|---|
| `nav.plans` | Тарифы |
| `nav.support` | Поддержка |
| `nav.login` | Войти |
| `nav.home` | На главную |
| `footer.about` | Подписка на доступ поверх собственной панели |
| `footer.sections` | Разделы |
| `footer.legal` | Правовая информация |
| `footer.rights` | Все права защищены |
| `consent.before` | Продолжая, вы принимаете |
| `consent.and` | и |

---

### Task 1: Шапка публичных страниц

**Files:**
- Create: `frontend/apps/web/src/components/public-header.tsx`
- Create: `frontend/apps/web/src/components/public-header.test.tsx`

**Interfaces:**
- Produces: `PublicHeader()` — шапка без свойств.

**Устройство.** Слева `Lockup` (существующий компонент) ссылкой на `/`. Справа ссылки «Тарифы» (`/plans`) и «Поддержка» (`/account/support`), `ThemeToggle` и кнопка «Войти» (`/login`). На узком экране текстовые ссылки скрываются (`hidden sm:flex`), лок-ап, переключатель темы и кнопка остаются: без переключателя человек не может сменить тему нигде на публичной части.

- [ ] **Step 1: Написать падающий тест**

`frontend/apps/web/src/components/public-header.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PublicHeader } from './public-header'

vi.mock('@/lib/browser-preferences', () => ({
  useBrowserPreferences: () => ({ language: 'ru', theme: 'light', setTheme: vi.fn() }),
}))

describe('шапка публичных страниц', () => {
  it('ведёт на главную, тарифы и вход', () => {
    render(<PublicHeader />)

    expect(screen.getByRole('link', { name: /на главную/i })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Тарифы' })).toHaveAttribute('href', '/plans')
    expect(screen.getByRole('link', { name: 'Войти' })).toHaveAttribute('href', '/login')
  })

  it('даёт сменить тему до входа', () => {
    render(<PublicHeader />)

    expect(screen.getByRole('button', { name: /тема/i })).toBeInTheDocument()
  })
})
```

Если `ThemeToggle` подписан иначе, посмотрите его разметку в `frontend/apps/web/src/components/theme-toggle.tsx` и приведите ожидание теста к настоящей подписи — но не наоборот: подпись существующего компонента менять не нужно.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: FAIL — компонента нет.

- [ ] **Step 3: Написать компонент**

`frontend/apps/web/src/components/public-header.tsx` — клиентский компонент (`'use client'`), собранный из `Lockup`, `ThemeToggle` и `Button` с `asChild`-ссылкой, если такая возможность у кнопки есть; иначе — обычная `<Link>` со стилем вторичной кнопки. Подписи берутся через `useTranslate(useBrowserLanguage())`, как это делает `frontend/apps/web/src/app/plans/page.tsx`.

Разметка: `<header className="border-border border-b">` с внутренним `<div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 py-4">`.

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: PASS.

- [ ] **Step 5: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

---

### Task 2: Подвал с правовыми ссылками

**Files:**
- Create: `frontend/apps/web/src/components/public-footer.tsx`
- Create: `frontend/apps/web/src/components/public-footer.test.tsx`

**Interfaces:**
- Consumes: `useLegalDocuments(language)` из `@repibot/core` (план `legal-public`).
- Produces: `PublicFooter()`.

**Устройство.** Слева `Lockup` и строка `footer.about`. Дальше колонка `footer.sections` со ссылками «Тарифы», «Войти», «Регистрация». Дальше колонка `footer.legal` со ссылками на документы — **только если список непустой**. Внизу строка «© <год> Re:Pibot. <footer.rights>».

- [ ] **Step 1: Написать падающий тест**

`frontend/apps/web/src/components/public-footer.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PublicFooter } from './public-footer'

const useLegalDocuments = vi.fn()

vi.mock('@repibot/core', () => ({
  useLegalDocuments: (language: string) => useLegalDocuments(language),
  translate: (_: string, key: string) => key,
}))

vi.mock('@/lib/browser-preferences', () => ({
  useBrowserPreferences: () => ({ language: 'ru', theme: 'light', setTheme: vi.fn() }),
}))

describe('подвал публичных страниц', () => {
  it('показывает правовые ссылки, когда документы заведены', () => {
    useLegalDocuments.mockReturnValue({
      data: [
        { slug: 'terms', title: 'Пользовательское соглашение', published_at: '2026-08-01' },
        { slug: 'privacy', title: 'Политика конфиденциальности', published_at: '2026-08-01' },
      ],
      isPending: false,
      isError: false,
    })

    render(<PublicFooter />)

    expect(screen.getByRole('link', { name: 'Пользовательское соглашение' })).toHaveAttribute(
      'href',
      '/legal/terms',
    )
    expect(screen.getByRole('link', { name: 'Политика конфиденциальности' })).toHaveAttribute(
      'href',
      '/legal/privacy',
    )
  })

  it('не рисует раздел целиком, когда документов нет', () => {
    useLegalDocuments.mockReturnValue({ data: [], isPending: false, isError: false })

    render(<PublicFooter />)

    expect(screen.queryByText('footer.legal')).not.toBeInTheDocument()
  })

  it('молчит и при неудачном запросе', () => {
    useLegalDocuments.mockReturnValue({ data: undefined, isPending: false, isError: true })

    render(<PublicFooter />)

    expect(screen.queryByText('footer.legal')).not.toBeInTheDocument()
    // Остальной подвал при этом на месте: недоступный API не должен уносить навигацию.
    expect(screen.getByRole('link', { name: 'Тарифы' })).toBeInTheDocument()
  })
})
```

Подписи «Тарифы», «Войти», «Регистрация» в тесте ожидаются через `translate`, которая в моке возвращает ключ. Приведите ожидания к тому, что реально рисует компонент: если ссылки подписаны ключами `nav.plans` и подобными, ожидайте их. Главное, что проверяется: колонка документов появляется и исчезает, а остальной подвал не зависит от запроса.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: FAIL — компонента нет.

- [ ] **Step 3: Написать компонент**

`frontend/apps/web/src/components/public-footer.tsx` — клиентский компонент.

Ключевое место, ради которого написан третий тест:

```tsx
  // Пустой раздел «Правовая информация» с нулём ссылок хуже его отсутствия,
  // а неудачный запрос ничем не отличается от «документов не завели»:
  // и в том и в другом случае показывать нечего.
  const documents = legal.data ?? []
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: PASS, три новых теста.

- [ ] **Step 5: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

---

### Task 3: Общий макет публичных страниц

**Files:**
- Create: `frontend/apps/web/src/app/(public)/layout.tsx`
- Move: `frontend/apps/web/src/app/page.tsx` → `frontend/apps/web/src/app/(public)/page.tsx`
- Move: `frontend/apps/web/src/app/page.test.tsx` → `frontend/apps/web/src/app/(public)/page.test.tsx`
- Move: `frontend/apps/web/src/app/plans/` → `frontend/apps/web/src/app/(public)/plans/`
- Move: `frontend/apps/web/src/app/legal/` → `frontend/apps/web/src/app/(public)/legal/`

**Interfaces:**
- Consumes: `PublicHeader` (Task 1), `PublicFooter` (Task 2).

- [ ] **Step 1: Перенести маршруты**

Перенесите четыре пути выше как есть, ничего в них не меняя, кроме относительных импортов, если такие найдутся (в проекте принят алиас `@/`, поэтому, скорее всего, менять нечего).

- [ ] **Step 2: Проверить, что адреса не изменились**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: PASS — существующие тесты страниц продолжают проходить, они не знают о переносе.

- [ ] **Step 3: Написать макет**

`frontend/apps/web/src/app/(public)/layout.tsx`:

```tsx
import type { ReactNode } from 'react'

import { PublicFooter } from '@/components/public-footer'
import { PublicHeader } from '@/components/public-header'

/**
 * Оболочка страниц, которые видит человек до входа.
 *
 * Группа в скобках не попадает в адрес: `/plans` и `/legal/terms` остались
 * там же, где были. Вход и регистрация сюда не входят намеренно — у них своя
 * центрированная компоновка, и шапка с подвалом её только растащили бы.
 */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <PublicHeader />
      <div className="flex-1">{children}</div>
      <PublicFooter />
    </div>
  )
}
```

- [ ] **Step 4: Убедиться, что всё проходит**

Run: `cd frontend && pnpm --filter @repibot/web test && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

---

### Task 4: Согласие с документами при регистрации

**Files:**
- Create: `frontend/apps/web/src/components/legal-consent.tsx`
- Create: `frontend/apps/web/src/components/legal-consent.test.tsx`
- Modify: `frontend/apps/web/src/app/(auth)/register/page.tsx`

**Interfaces:**
- Consumes: `useLegalDocuments(language)`.
- Produces: `LegalConsent()` — строка под кнопкой; ничего не рисует, если документов нет.

**Почему без галочки.** Согласие выражается действием — нажатием кнопки регистрации. Обязательная галочка добавляет шаг и ничего не добавляет к доказательству: и то и другое одинаково фиксируется фактом создания аккаунта, а версия действовавшего текста хранится в `legal_documents`.

- [ ] **Step 1: Написать падающий тест**

`frontend/apps/web/src/components/legal-consent.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LegalConsent } from './legal-consent'

const useLegalDocuments = vi.fn()

vi.mock('@repibot/core', () => ({
  useLegalDocuments: (language: string) => useLegalDocuments(language),
  translate: (_: string, key: string) => key,
}))

vi.mock('@/lib/browser-preferences', () => ({
  useBrowserPreferences: () => ({ language: 'ru', theme: 'light', setTheme: vi.fn() }),
}))

describe('согласие с документами', () => {
  it('перечисляет заведённые документы ссылками', () => {
    useLegalDocuments.mockReturnValue({
      data: [
        { slug: 'terms', title: 'Пользовательским соглашением', published_at: '2026-08-01' },
        { slug: 'privacy', title: 'Политикой конфиденциальности', published_at: '2026-08-01' },
      ],
      isPending: false,
      isError: false,
    })

    render(<LegalConsent />)

    expect(screen.getByRole('link', { name: 'Пользовательским соглашением' })).toHaveAttribute(
      'href',
      '/legal/terms',
    )
    expect(screen.getByRole('link', { name: 'Политикой конфиденциальности' })).toBeInTheDocument()
  })

  it('молчит, когда документов нет', () => {
    useLegalDocuments.mockReturnValue({ data: [], isPending: false, isError: false })

    const { container } = render(<LegalConsent />)

    expect(container).toBeEmptyDOMElement()
  })
})
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: FAIL — компонента нет.

- [ ] **Step 3: Написать компонент**

`frontend/apps/web/src/components/legal-consent.tsx` — клиентский компонент. Возвращает `null` при пустом списке. Иначе — `<p className="mt-4 text-caption text-text-muted">` с текстом `consent.before`, перечислением ссылок через запятую и `consent.and` перед последней.

- [ ] **Step 4: Вставить в форму регистрации**

В `frontend/apps/web/src/app/(auth)/register/page.tsx` добавить `<LegalConsent />` сразу под кнопкой отправки, не меняя саму форму и её обработчики.

- [ ] **Step 5: Убедиться, что тесты проходят**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: PASS.

- [ ] **Step 6: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

---

### Task 5: Открытая графика, robots и карта сайта

**Files:**
- Modify: `frontend/apps/web/src/app/layout.tsx`
- Create: `frontend/apps/web/src/app/robots.ts`
- Create: `frontend/apps/web/src/app/sitemap.ts`
- Create: `frontend/apps/web/src/app/sitemap.test.ts`
- Copy: `docs/design/logo/raster/og-image.png` → `frontend/apps/web/public/og-image.png`
- Modify: `tools/tests/test_brand.py`

**Interfaces:**
- Consumes: `fetchFromApi` (план `legal-public`).
- Produces: `robots.txt`, `sitemap.xml`, метаданные `openGraph` и `twitter`.

- [ ] **Step 1: Написать падающий тест карты сайта**

`frontend/apps/web/src/app/sitemap.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'

import sitemap from './sitemap'

const fetchFromApi = vi.fn()

vi.mock('@/lib/server-api', () => ({ fetchFromApi: (path: string) => fetchFromApi(path) }))

beforeEach(() => fetchFromApi.mockReset())

describe('карта сайта', () => {
  it('перечисляет главную, тарифы и опубликованные документы', async () => {
    fetchFromApi.mockResolvedValue([
      { slug: 'terms', title: 'Условия', published_at: '2026-08-01T00:00:00Z' },
    ])

    const entries = await sitemap()

    expect(entries.map((entry) => entry.url)).toEqual([
      'http://localhost/',
      'http://localhost/plans',
      'http://localhost/legal/terms',
    ])
  })

  it('не содержит кабинета и админки', async () => {
    fetchFromApi.mockResolvedValue([])

    const urls = (await sitemap()).map((entry) => entry.url).join(' ')

    expect(urls).not.toContain('/account')
    expect(urls).not.toContain('/admin')
    expect(urls).not.toContain('/login')
  })

  it('отдаёт статические адреса, когда API недоступен', async () => {
    fetchFromApi.mockResolvedValue(null)

    expect(await sitemap()).toHaveLength(2)
  })
})
```

Базовый адрес берётся из `NEXT_PUBLIC_SITE_URL` со значением по умолчанию `http://localhost`. Если тест ожидает другое умолчание — приведите ожидание к коду, но умолчание оставьте на `http://localhost`: домен известен только развернувшему.

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: FAIL — модуля `sitemap` нет.

- [ ] **Step 3: Написать карту сайта и robots**

`frontend/apps/web/src/app/sitemap.ts`:

```ts
import type { MetadataRoute } from 'next'

import { fetchFromApi } from '@/lib/server-api'

interface LegalListItem {
  slug: string
  title: string
  published_at: string
}

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost'

/**
 * Карта сайта: только то, что имеет смысл показывать поисковику.
 *
 * Кабинет, админка, вход и регистрация исключены: за ними ничего нет без
 * сессии, а их присутствие в карте — приглашение перебирать логины.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const documents = (await fetchFromApi<LegalListItem[]>('/api/legal')) ?? []

  return [
    { url: `${SITE_URL}/`, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE_URL}/plans`, changeFrequency: 'weekly', priority: 0.8 },
    ...documents.map((document) => ({
      url: `${SITE_URL}/legal/${document.slug}`,
      lastModified: new Date(document.published_at),
      changeFrequency: 'yearly' as const,
      priority: 0.3,
    })),
  ]
}
```

`frontend/apps/web/src/app/robots.ts`:

```ts
import type { MetadataRoute } from 'next'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      // Закрыто не ради секретности — эти адреса и так требуют сессии, — а
      // чтобы обходчик не тратил лимит на страницы, где ему нечего забрать.
      disallow: ['/account', '/admin', '/api'],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  }
}
```

- [ ] **Step 4: Добавить открытую графику**

В `frontend/apps/web/src/app/layout.tsx` дополнить `metadata`:

```ts
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost'),
  openGraph: {
    title: 'Re:Pibot',
    description: 'Подписка на доступ. Одна ссылка — все устройства.',
    type: 'website',
    images: [{ url: '/og-image.png', width: 1200, height: 630 }],
  },
  twitter: { card: 'summary_large_image', images: ['/og-image.png'] },
```

- [ ] **Step 5: Положить картинку и расширить тест бренда**

Скопируйте `docs/design/logo/raster/og-image.png` в `frontend/apps/web/public/og-image.png`.

В `tools/tests/test_brand.py` в параметризацию `test_public_raster_matches_the_brand_kit` добавьте `"og-image.png"` — тест сверяет копии с брендовым набором, и картинка, разошедшаяся с оригиналом, иначе не заметится.

- [ ] **Step 6: Убедиться, что всё проходит**

Run: `cd frontend && pnpm --filter @repibot/web test`
Expected: PASS, три новых теста.

Run: `uv run pytest tools/tests/test_brand.py -q`
Expected: PASS.

- [ ] **Step 7: Проверить типы и линтеры**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Run: `uv run ruff check tools && uv run ruff format --check tools`
Expected: без замечаний.

---

## Готовность плана

После пяти задач у публичной части есть шапка, подвал и правовые ссылки, которые появляются вместе с документами и исчезают вместе с ними; сайт отдаёт `robots.txt`, `sitemap.xml` и картинку для превью ссылки. Место для лендинга готово — им занимается следующий план.
