# Кабинет: каркас и якорный экран

> **Для исполнителя:** план выполняется задача за задачей. Шаги помечены `- [ ]`.

**Цель:** переделать оболочку кабинета и экран подписки — первый экран, на котором проверяется вся система целиком.

**Устройство:** экран подписки выбран якорем не случайно: в нём собрано всё сложное разом — состояние с загрузкой и отказом, карточка с QR, полоса трафика, список устройств и диалог подтверждения. Если система держит его, она держит остальные. Остальные экраны кабинета переделываются отдельным планом и в этом не трогаются.

**Стек:** Next.js 16 (App Router), React 19, TanStack Query 5, Tailwind 4, vitest.

## Общие ограничения

- **Ветка `dev`.** Никаких git-команд: коммиты делает ведущий после проверки задачи.
- **Только свои файлы.** Соседние планы в это же время правят `app/(auth)`, `app/admin`, `app/account/{page,notifications,payments,security,support}` и весь `apps/miniapp`. Туда не заходить даже ради однострочной правки.
- **Никакого прогона проверок по всему репозиторию.** Только свои тесты: `pnpm --filter @repibot/web vitest run <файл>`.
- **Существующие тесты — договор.** `apps/web/src/app/account/subscription/page.test.tsx` обязан остаться зелёным. Если он упал — сначала доказать, что поведение изменилось намеренно, и только потом трогать тест.
- **Кегли — только по шкале бренда:** `text-display`, `text-h1`, `text-h2`, `text-h3`, `text-body`, `text-small`, `text-caption`. `text-sm`, `text-lg`, `text-xl`, `text-2xl` и прочие встроенные погашены — написанные по привычке, они молча не сработают.
- **Начертание ставится классом:** `font-semibold` к `text-h1`/`text-h2`, `font-medium` к `text-h3`. В токенах шкалы его нет намеренно.
- **Цвета — только токенами.** Никаких `text-gray-500`.
- **Иконки — через `Icon` из `@repibot/ui`.** Имена значков сверять по `node_modules/@hugeicons/core-free-icons/dist/index.d.ts`, наугад не писать: несуществующее имя даст `undefined` и пустую иконку без ошибки сборки.
- **Тексты — из словарей.** Новых ключей этот план не заводит: всё, что нужно, уже переведено.
- **Комментарии по-русски и о том, почему.** Никаких `// biome-ignore` без сработавшего правила.

## Что уже готово

В `@repibot/ui` есть: `Alert`, `Badge`, `Button`, `Card`, `Dialog`, `DropdownMenu`, `EmptyState`, `FormField`, `Icon`, `Input`, `LogoMark`, `PasswordInput`, `Select`, `Skeleton`, `Spinner`, `Switch`, `Table`, `Tabs`, `Textarea`, `Tooltip`.

Подписи к состояниям:

```tsx
<Spinner label={t('common.loading')} />
<Alert tone="error">{errorText(query.error, language)}</Alert>
```

## Карта файлов

| Файл | Что с ним делаем |
|---|---|
| `apps/web/src/components/account-shell.tsx` | Боковая навигация с иконками, настоящая шапка |
| `apps/web/src/components/account-shell.test.tsx` | Создать: сегодня оболочка не покрыта ничем |
| `apps/web/src/app/account/subscription/page.tsx` | Состояния на `Spinner` и `Alert`, заголовок по шкале |
| `apps/web/src/components/subscription-card.tsx` | Статус — `Badge`, место QR — `Skeleton` |
| `apps/web/src/components/traffic-bar.tsx` | Шкала кеглей, состояния |
| `apps/web/src/components/device-list.tsx` | Шкала кеглей, состояния, `Alert` |

---

### Задача 1: Каркас кабинета

**Файлы:**
- Изменить: `frontend/apps/web/src/components/account-shell.tsx`
- Создать: `frontend/apps/web/src/components/account-shell.test.tsx`

**Интерфейсы:**
- Потребляет: `useLogout`, `useProfileLanguage`, `useTranslate`, `AuthGuard`, `Lockup`, `ThemeToggle` — всё уже существует и подключено.
- Отдаёт: `AccountShell({ children })` — сигнатура не меняется. Экранам кабинета по-прежнему достаточно отдать своё содержимое.

Сегодня оболочка — колонка `max-w-3xl`, шапка с локапом и выходом, под ней шесть текстовых ссылок вперемешку. Становится: от `md` — постоянный столбец навигации слева, содержимое справа; ниже `md` столбец схлопывается в горизонтальную полосу с прокруткой.

В шапку добавляется переключатель темы. Сейчас он существует ровно в одном месте — на странице-заглушке лендинга, — и вошедший человек сменить тему не может нигде. Языка в шапке нет намеренно: он живёт на странице профиля и хранится в учётной записи, а второй такой же переключатель означал бы два места для одного значения.

- [ ] **Шаг 1: Написать падающий тест**

Создать `frontend/apps/web/src/components/account-shell.test.tsx`. За образцом устройства теста — `admin-shell.test.tsx` рядом: там уже решено, как подменять `next/navigation` и запросы.

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AccountShell } from './account-shell'

vi.mock('next/navigation', () => ({
  usePathname: () => '/account/subscription',
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

vi.mock('./auth-guard', () => ({
  AuthGuard: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('@repibot/core', async () => ({
  ...(await vi.importActual<typeof import('@repibot/core')>('@repibot/core')),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useMe: () => ({ data: { language: 'ru' } }),
}))

describe('AccountShell', () => {
  it('показывает все шесть разделов', () => {
    render(<AccountShell>содержимое</AccountShell>)

    const nav = screen.getByRole('navigation')
    expect(screen.getAllByRole('link').filter((link) => nav.contains(link))).toHaveLength(6)
  })

  it('отмечает текущий раздел для скринридера, а не только краской', () => {
    render(<AccountShell>содержимое</AccountShell>)

    expect(screen.getByRole('link', { current: 'page' })).toHaveAttribute(
      'href',
      '/account/subscription',
    )
  })

  it('даёт сменить тему изнутри кабинета', () => {
    /* До этой правки переключатель существовал только на странице-заглушке
       лендинга: вошедший человек сменить тему не мог нигде. */
    render(<AccountShell>содержимое</AccountShell>)

    expect(screen.getByRole('button', { name: /тем/i })).toBeInTheDocument()
  })

  it('показывает содержимое страницы', () => {
    render(<AccountShell>содержимое</AccountShell>)

    expect(screen.getByText('содержимое')).toBeInTheDocument()
  })
})
```

Перед запуском открыть `theme-toggle.tsx` и посмотреть, какой у кнопки доступный текст: проверку в тесте подогнать под действительность, а не наоборот.

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm --filter @repibot/web vitest run src/components/account-shell.test.tsx`
Ожидается: падение на проверке темы — переключателя в оболочке нет.

- [ ] **Шаг 3: Переписать оболочку**

Заменить `AccountFrame` в `account-shell.tsx`. Ссылки — те же шесть, порядок тот же, к каждой добавляется иконка:

```tsx
const LINKS = [
  { href: '/account', key: 'account.title', icon: UserIcon },
  { href: '/account/subscription', key: 'subscription.title', icon: ShieldKeyIcon },
  { href: '/account/payments', key: 'payment.title', icon: CreditCardIcon },
  { href: '/account/security', key: 'account.security', icon: LockIcon },
  { href: '/account/notifications', key: 'notifications.title', icon: Notification01Icon },
  { href: '/account/support', key: 'support.title', icon: BubbleChatIcon },
] as const
```

Имена значков выше — предположение. Проверить каждое по `node_modules/@hugeicons/core-free-icons/dist/index.d.ts` и заменить на существующие; несуществующее имя даст пустую иконку без единой жалобы сборки.

Разметка:

```tsx
  return (
    <div className="min-h-dvh bg-bg">
      <header className="border-border-subtle border-b bg-surface">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <Lockup size={28} />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="ghost" size="sm" onClick={signOut} disabled={logout.isPending}>
              {t('account.logout')}
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 md:flex-row md:gap-8">
        <nav
          aria-label={t('account.title')}
          // Ниже md столбец схлопывается в полосу с прокруткой: шесть
          // разделов в колонку на телефоне съели бы весь первый экран.
          className="-mx-4 flex gap-1 overflow-x-auto px-4 md:mx-0 md:w-56 md:shrink-0 md:flex-col md:overflow-x-visible md:px-0"
        >
          {LINKS.map((link) => {
            const current = pathname === link.href
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={current ? 'page' : undefined}
                className={cn(
                  'flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-small transition-colors',
                  current
                    ? 'bg-jade-mist font-medium text-text-accent'
                    : 'text-text-secondary hover:bg-surface-sunken hover:text-text',
                )}
              >
                <Icon icon={link.icon} size={20} />
                {t(link.key)}
              </Link>
            )
          })}
        </nav>

        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  )
```

`cn` берётся из `@repibot/ui`, он там уже выставлен наружу.

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm --filter @repibot/web vitest run src/components/account-shell.test.tsx`
Ожидается: PASS всех четырёх проверок.

---

### Задача 2: Экран подписки

**Файлы:**
- Изменить: `frontend/apps/web/src/app/account/subscription/page.tsx`
- Изменить: `frontend/apps/web/src/app/account/subscription/page.test.tsx` — только если он упадёт и падение окажется законным

**Интерфейсы:**
- Потребляет: `Spinner`, `Alert`, `Button`, `EmptyState` из `@repibot/ui`.
- Отдаёт: образец страницы кабинета, который повторят остальные пять экранов: `<main className="flex flex-col gap-6">`, заголовок `text-h1 font-semibold`, дальше карточки.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/subscription/page.test.tsx`
Ожидается: PASS. Это исходное состояние; после правки оно обязано повториться.

- [ ] **Шаг 2: Переписать состояния и заголовок**

Заголовок: `className="text-h1 font-semibold text-text"` вместо `text-2xl font-semibold`.

Обёртка: `<main className="flex flex-col gap-6">` вместо `gap-4` — между группами шесть, внутри группы три.

Загрузка: вместо абзаца с `role="status"`

```tsx
        <Spinner label={t('common.loading')} />
```

Отказ подписки и отказ триала — оба через `Alert`:

```tsx
        <Alert tone="error">{errorText(subscription.error, language)}</Alert>
```

```tsx
      {trial.error === null ? null : (
        <Alert tone="error">{errorText(trial.error, language)}</Alert>
      )}
```

Ссылка на платежи перестаёт быть подчёркнутым текстом посреди страницы и становится второстепенной кнопкой — на экране с двумя карточками подчёркнутая строка между ними читается как обрывок:

```tsx
      <div>
        <Button asChild variant="secondary" size="sm">
          <Link href="/account/payments">{t('payment.title')}</Link>
        </Button>
      </div>
```

- [ ] **Шаг 3: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/subscription/page.test.tsx`
Ожидается: PASS. Если тест ищет текст «Загрузка…» напрямую — он законно упал: `Spinner` объявляет то же самое через `aria-label`, и проверку надо перевести на `getByRole('status', { name: ... })`. Любое другое падение означает, что правка задела поведение, и чинить нужно правку.

---

### Задача 3: Карточка подписки

**Файлы:**
- Изменить: `frontend/apps/web/src/components/subscription-card.tsx`

**Интерфейсы:**
- Потребляет: `Badge`, `Skeleton`, `Alert` из `@repibot/ui`.
- Отдаёт: карточку, в которой статус подписки виден бейджем. Тот же приём и та же таблица тонов повторяются на экране подписки в MiniApp — соседний план опирается на неё.

Статус сейчас набран акцентным текстом под названием тарифа: «активна» и «истекла» отличаются только словом, набранным одинаково зелёным. Становится бейджем, и тон зависит от состояния:

| Статус | Тон |
|---|---|
| `active` | `success` |
| `trial` | `info` |
| `pending_provision` | `warning` |
| `expired`, `disabled` | `danger` |
| прочее | `neutral` |

- [ ] **Шаг 1: Написать падающий тест**

Создать `frontend/apps/web/src/components/subscription-card.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SubscriptionCard, type Subscription } from './subscription-card'

const BASE: Subscription = {
  plan_code: 'month',
  plan_name: { ru: 'Месяц', en: 'Month' },
  status: 'active',
  started_at: '2026-08-01T00:00:00Z',
  expires_at: '2026-09-01T00:00:00Z',
  subscription_url: null,
  traffic_limit_bytes: 0,
  hwid_device_limit: 3,
}

describe('SubscriptionCard', () => {
  it('показывает название тарифа заголовком раздела', () => {
    render(<SubscriptionCard subscription={BASE} language="ru" />)

    expect(screen.getByRole('heading', { name: 'Месяц' })).toBeInTheDocument()
  })

  it('истёкшая подписка не выглядит так же, как действующая', () => {
    /* До правки оба состояния были набраны одним акцентным цветом и
       отличались только словом. */
    const { container: active } = render(<SubscriptionCard subscription={BASE} language="ru" />)
    const { container: expired } = render(
      <SubscriptionCard subscription={{ ...BASE, status: 'expired' }} language="ru" />,
    )

    const tone = (root: HTMLElement) =>
      root.querySelector('span.inline-flex.rounded-full')?.className ?? ''
    expect(tone(active)).not.toBe(tone(expired))
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm --filter @repibot/web vitest run src/components/subscription-card.test.tsx`
Ожидается: падение на втором случае — бейджа нет, оба класса пустые и потому равны.

- [ ] **Шаг 3: Заменить статус бейджем**

Добавить рядом с `statusText`:

```tsx
/* Тон бейджа по состоянию подписки. `pending_provision` — не отказ: панель
   ещё выдаёт доступ, и красный здесь напугал бы человека зря. */
function statusTone(status: string): BadgeTone {
  switch (status) {
    case 'active':
      return 'success'
    case 'trial':
      return 'info'
    case 'pending_provision':
      return 'warning'
    case 'expired':
    case 'disabled':
      return 'danger'
    default:
      return 'neutral'
  }
}
```

В разметке шапки карточки заменить абзац со статусом:

```tsx
          <h2 id="current-subscription-title" className="text-h2 font-semibold text-text">
            {planName(subscription, language)}
          </h2>
          <div className="mt-2">
            <Badge tone={statusTone(subscription.status)}>
              {statusText(subscription.status, language)}
            </Badge>
          </div>
```

- [ ] **Шаг 4: Перевести остальное на шкалу**

В том же файле: `text-xs` → `text-caption`, `text-sm` → `text-small`. Мест шесть: подпись «действует до», сама дата, подпись ссылки, ссылка, состояние копирования (обе ветки) и текст ожидания выдачи.

Место QR во время загрузки — `Skeleton` вместо пустого прямоугольника, а отказ QR — `Alert`:

```tsx
          {qr.status === 'loading' ? (
            <Skeleton className="aspect-square w-full" />
          ) : qr.status === 'error' ? (
            <Alert tone="error">
              {language === 'ru'
                ? 'Не удалось создать QR-код. Скопируйте ссылку подключения.'
                : 'Could not create the QR code. Copy the connection link instead.'}
            </Alert>
          ) : (
```

Прежний прямоугольник объявлял себя через `role="status"`. `Skeleton` от скринридера скрыт намеренно — он не содержит сведений, — и это не потеря: рядом уже есть ссылка подключения, ради которой QR и рисуется.

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Запустить: `pnpm --filter @repibot/web vitest run src/components/subscription-card.test.tsx src/app/account/subscription/page.test.tsx`
Ожидается: PASS обоих файлов.

---

### Задача 4: Трафик и устройства

**Файлы:**
- Изменить: `frontend/apps/web/src/components/traffic-bar.tsx`
- Изменить: `frontend/apps/web/src/components/device-list.tsx`

**Интерфейсы:**
- Потребляет: `Spinner`, `Alert`, `Skeleton` из `@repibot/ui`.
- Отдаёт: два раздела якорного экрана в общем виде. Ничего наружу не экспортирует сверх того, что уже есть.

- [ ] **Шаг 1: Перевести полосу трафика**

В `traffic-bar.tsx`:

- заголовок: `text-lg font-semibold` → `text-h3 font-medium`. Внутри карточки заголовок второго уровня не должен спорить с заголовком страницы;
- загрузка: абзац `role="status"` → `<Spinner label={translate(language, 'common.loading')} className="mt-4 block" />`;
- отказ: абзац `role="alert"` → `<Alert tone="error" className="mt-4">{errorText(traffic.error, language)}</Alert>`;
- `text-sm` → `text-small` (четыре места), `text-xs` → `text-caption` (одно).

Сама полоса с `role="progressbar"` остаётся как есть: она уже размечена верно, и трогать её нечего.

- [ ] **Шаг 2: Перевести список устройств**

В `device-list.tsx`:

- заголовок: `text-lg font-semibold` → `text-h3 font-medium`;
- счётчик устройств, подписи и пояснения: `text-sm` → `text-small` (четыре места);
- отказ отвязки и отказ загрузки — оба через `Alert tone="error"`;
- загрузка — `Spinner`;
- вместо `Spinner` при загрузке списка лучше поставить три `Skeleton` строкой: форма будущего содержимого здесь известна заранее, и заглушка по форме списка не заставляет разметку прыгать, когда данные приедут:

```tsx
        {devices.isPending ? (
          <ul className="mt-4 divide-y divide-border-subtle">
            {[0, 1, 2].map((row) => (
              <li key={row} className="flex items-center justify-between gap-3 py-4">
                <div className="flex-1">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="mt-2 h-3 w-24" />
                </div>
                <Skeleton className="h-8 w-24" />
              </li>
            ))}
          </ul>
        ) : ...
```

Кнопка отвязки уже несёт `aria-label` с названием устройства — этого достаточно, `Tooltip` здесь не нужен: подпись у кнопки есть словами.

- [ ] **Шаг 3: Убедиться, что якорный экран цел**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/subscription/ src/components/`
Ожидается: PASS. Это последняя задача плана — весь якорный экран со всеми частями должен быть зелёным.

- [ ] **Шаг 4: Проверить типы**

Запустить: `pnpm --filter @repibot/web typecheck`
Ожидается: PASS.
