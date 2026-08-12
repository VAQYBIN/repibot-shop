# Сторож шкалы и сквозной обход экранов

> **Для исполнителя:** план выполняется задача за задачей. Шаги помечены `- [ ]`.

**Цель:** запереть шкалу кеглей тестом и провести браузер по всем тридцати экранам в обеих темах.

**Устройство:** подпроект начался с того, что встроенные размеры Tailwind были погашены. Погашенный класс не ломает сборку — он просто не превращается ни во что, поэтому забытый `text-sm` до сих пор мог остаться незамеченным. Сторож обходит исходники и находит их все разом; его первое падение и есть список недоделок. Обход браузером ловит другое: ошибки в консоли и разметку, уехавшую вбок.

**Стек:** vitest, Playwright, Docker-контур `repibot-e2e`.

## Общие ограничения

- **Ветка `dev`.** Никаких git-команд: коммиты делает ведущий после проверки задачи.
- **Этот план идёт последним.** Все экраны уже переделаны соседними планами. Если сторож находит остаток — его чинит этот план, но только сам остаток: переделывать экран заново не нужно.
- **Прогон проверок здесь разрешён и обязателен** — соседи закончили.
- **Сквозному обходу нужен Docker.** Стек поднимает `globalSetup`; обычный стек разработчика при этом останавливать не нужно, контур свой.
- **Комментарии по-русски и о том, почему.** Никаких `// biome-ignore` без сработавшего правила.

---

### Задача 1: Сторож погашенных кеглей

**Файлы:**
- Изменить: `frontend/packages/ui/src/theme.test.ts`
- Изменить: любые файлы, где сторож найдёт остаток

**Интерфейсы:**
- Потребляет: ничего.
- Отдаёт: тест, который падает при появлении встроенного имени кегля где угодно в исходниках.

- [ ] **Шаг 1: Написать падающий тест**

В конец `packages/ui/src/theme.test.ts`:

```ts
import { readdirSync } from 'node:fs'

/** Имена, погашенные строкой `--text-*: initial` в theme.css. */
const RETIRED = ['xs', 'sm', 'base', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', '7xl', '8xl', '9xl']

const ROOTS = [
  resolve(process.cwd(), 'src'),
  resolve(process.cwd(), '../../apps/web/src'),
  resolve(process.cwd(), '../../apps/miniapp/src'),
]

function sources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = resolve(directory, entry.name)
    if (entry.isDirectory()) return sources(full)
    return /\.(tsx?|css)$/.test(entry.name) ? [full] : []
  })
}

describe('шкала кеглей заперта', () => {
  /* Погашенный класс не ломает сборку: Tailwind молча ничего для него не
     выпускает, и текст остаётся унаследованного размера. Заметить это на
     глаз можно не всегда — поэтому сторож. */
  it('во всех исходниках не осталось встроенных имён кегля', () => {
    const pattern = new RegExp(`\\btext-(${RETIRED.join('|')})\\b`)
    const guilty: string[] = []

    for (const root of ROOTS) {
      for (const file of sources(root)) {
        const line = readFileSync(file, 'utf8')
          .split('\n')
          .findIndex((text) => pattern.test(text))
        if (line >= 0) guilty.push(`${file}:${line + 1}`)
      }
    }

    expect(guilty).toEqual([])
  })
})
```

Файлы тестов исключать не нужно: в тесте `text-sm` встречается только как ожидание, а таких ожиданий после переделки остаться не должно.

- [ ] **Шаг 2: Запустить и получить список недоделок**

Запустить: `pnpm --filter @repibot/ui vitest run src/theme.test.ts`
Ожидается: либо PASS — тогда шкала действительно заперта, — либо падение со списком мест. Список и есть работа следующего шага.

- [ ] **Шаг 3: Подчистить найденное**

Каждое место заменить по соответствию: `text-xs` → `text-caption`, `text-sm` → `text-small`, `text-base` → `text-body`, `text-lg` → `text-h3`, `text-xl` → `text-h2`, `text-2xl` → `text-h1`, `text-3xl` и крупнее → `text-display`.

Если остаток нашёлся в тесте как ожидание — поправить ожидание, а не возвращать класс.

- [ ] **Шаг 4: Убедиться, что сторож зелёный**

Запустить: `pnpm --filter @repibot/ui vitest run src/theme.test.ts`
Ожидается: PASS.

- [ ] **Шаг 5: Убедиться, что подчистка ничего не сломала**

Запустить: `pnpm --filter @repibot/web vitest run && pnpm --filter @repibot/miniapp vitest run`
Ожидается: PASS обоих приложений.

---

### Задача 2: Сквозной обход веба

**Файлы:**
- Создать: `frontend/apps/web/e2e/sweep.spec.ts`

**Интерфейсы:**
- Потребляет: `seed`, `querySql` из `./seed`, `WEB_URL` из `./stack`.
- Отдаёт: проверку, которую не делает ни один тест компонента: страница действительно собирается в браузере и не едет вбок.

Обход проверяет три вещи на каждом экране:

1. в консоли браузера нет сообщений уровня `error`;
2. страница не уехала вбок: `scrollWidth` не превышает `clientWidth` больше чем на пиксель;
3. на странице есть заголовок первого уровня.

Третья проверка выглядит мелочью, но ловит настоящую поломку: страница, отдавшая пустую разметку из-за упавшего запроса, выглядит как «просто пусто» и молча проходит любой тест компонента.

- [ ] **Шаг 1: Написать обход**

```ts
import { expect, type Page, test } from '@playwright/test'

/** Экраны, доступные без входа. */
const PUBLIC = ['/plans', '/legal/terms', '/login', '/register', '/forgot-password']

/** Экраны, требующие сессии. */
const PRIVATE = [
  '/account',
  '/account/subscription',
  '/account/payments',
  '/account/security',
  '/account/notifications',
  '/account/support',
]

/** Экраны админки; открываются только сотрудником. */
const ADMIN = [
  '/admin',
  '/admin/users',
  '/admin/tickets',
  '/admin/payments',
  '/admin/broadcasts',
  '/admin/nodes',
]

const THEMES = ['light', 'dark'] as const

async function visit(page: Page, path: string, theme: string): Promise<void> {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })

  await page.addInitScript((value) => {
    // Тема ставится до первой отрисовки: иначе первый кадр всегда светлый,
    // и тёмная половина обхода проверяла бы светлую разметку.
    document.documentElement.dataset.theme = value
  }, theme)

  await page.goto(path)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  const overflow = await page.evaluate(() => {
    const root = document.scrollingElement
    return root === null ? 0 : root.scrollWidth - root.clientWidth
  })
  expect(overflow, `${path} уехала вбок на ${overflow}px`).toBeLessThanOrEqual(1)

  expect(errors, `${path}: ошибки в консоли`).toEqual([])
}

for (const theme of THEMES) {
  test(`публичные экраны, тема ${theme}`, async ({ page }) => {
    for (const path of PUBLIC) await visit(page, path, theme)
  })
}
```

Экраны за входом требуют сессии. Как её получить, уже решено в `auth.spec.ts` — повторить оттуда способ регистрации и входа, а не изобретать свой. Права сотрудника даёт `grantE2eAdmin` из `./seed`.

- [ ] **Шаг 2: Дописать закрытые экраны**

Два дополнительных теста на тему: один проходит `PRIVATE` после входа обычным человеком, второй — `ADMIN` после `grantE2eAdmin`.

Экран `/admin/users/[id]` открывается переходом из списка, а не по адресу: номер человека в контуре заранее не известен. Открыть первую строку таблицы нажатием и проверить её теми же тремя проверками.

- [ ] **Шаг 3: Прогнать обход**

Запустить: `pnpm --filter @repibot/web e2e sweep`
Ожидается: PASS. Первый прогон почти наверняка найдёт горизонтальную прокрутку на узких экранах — это и есть польза обхода; чинить надо разметку, а не порог в пикселях.

---

### Задача 3: Обход MiniApp

**Файлы:**
- Изменить: `frontend/apps/web/e2e/sweep.spec.ts`
- Создать: `frontend/apps/web/e2e/telegram.ts`

**Интерфейсы:**
- Отдаёт: `signInitData(user: { id: number; username: string }): string` — подписанные данные входа для подставного Телеграма.

Семь экранов MiniApp — те самые, где переделка глубже всего, и без этого шага они остались бы непроверенными вовсе. Вход в MiniApp требует подписанного `initData`, но токен бота в контуре свой и известен из `e2e/stack.env` (`BOT_TOKEN=0:e2e-bot-token`), поэтому подпись собирается локально.

- [ ] **Шаг 1: Написать подпись**

Создать `e2e/telegram.ts`:

```ts
import { createHmac } from 'node:crypto'

/** Токен подставного бота из stack.env. Секретом не является. */
const BOT_TOKEN = '0:e2e-bot-token'

/**
 * Подпись initData по правилам Telegram: ключ выводится из токена бота,
 * а не берётся им самим, и поле hash в подсчёт не входит.
 */
export function signInitData(user: { id: number; username: string }): string {
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: 'AAE',
    user: JSON.stringify({ id: user.id, first_name: 'E2E', username: user.username }),
  }

  const check = Object.keys(fields)
    .sort()
    .map((key) => `${key}=${fields[key]}`)
    .join('\n')
  const secret = createHmac('sha256', 'WebAppData').update(BOT_TOKEN).digest()
  const hash = createHmac('sha256', secret).update(check).digest('hex')

  return new URLSearchParams({ ...fields, hash }).toString()
}
```

Способ вывода ключа сверить с тем, как его проверяет бэкенд: `backend/core/src/repibot_core/integrations/telegram/`. Если там иначе — прав бэкенд, а не этот файл.

- [ ] **Шаг 2: Подставить Телеграм в браузер**

В обходе — заглушка окружения перед загрузкой страницы:

```ts
  await page.addInitScript((initData) => {
    const noop = () => undefined
    window.Telegram = {
      WebApp: {
        initData,
        initDataUnsafe: { user: { language_code: 'ru' } },
        colorScheme: 'light',
        ready: noop,
        expand: noop,
        openLink: noop,
        openTelegramLink: noop,
        onEvent: noop,
        offEvent: noop,
        MainButton: {
          setText: noop, show: noop, hide: noop, enable: noop, disable: noop,
          showProgress: noop, hideProgress: noop, onClick: noop, offClick: noop,
        },
        HapticFeedback: { notificationOccurred: noop, impactOccurred: noop },
      },
    }
  }, initData)
```

Заглушка обязана содержать `MainButton`: без неё обход прошёл бы по запасной ветке с обычной кнопкой и не проверил ровно то, что переделано.

- [ ] **Шаг 3: Завести человека с номером Телеграма**

Номер из подписи должен принадлежать существующему человеку, иначе вход вернёт отказ. Завести его через `runSql` из `./seed` — тем же приёмом, каким `grantE2eAdmin` выдаёт права.

- [ ] **Шаг 4: Пройти по семи экранам**

```ts
const MINIAPP = ['/app/', '/app/subscription', '/app/devices', '/app/payments', '/app/profile', '/app/support', '/app/winback']
```

Проверки те же три. Ширину окна поставить телефонной — `page.setViewportSize({ width: 390, height: 844 })`: MiniApp живёт только там, и проверять его на ширине ноутбука бессмысленно.

- [ ] **Шаг 5: Прогнать обход целиком**

Запустить: `pnpm --filter @repibot/web e2e sweep`
Ожидается: PASS всех тем и всех наборов экранов.

- [ ] **Шаг 6: Прогнать проверку целиком**

Запустить: `uv run check`
Ожидается: PASS. Это единственная команда проверки в проекте: линтеры, типы и тесты обоих языков. Соседи закончили, и запрет на полный прогон больше не действует.
