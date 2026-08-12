# Свой лендинг при развёртывании

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** развернувший проект у себя может подменить главную своей страницей, положив файлы в каталог, — без пересборки образов и без Node.

**Architecture:** подмена делается в nginx. Корневая локация сначала пробует отдать `index.html` из смонтированного каталога и лишь потом уходит в приложение. Пустой каталог означает штатный лендинг: наличие файла и есть переключатель.

**Tech Stack:** nginx, Docker Compose, Playwright.

## Global Constraints

- **Не выполняйте git-команд.** Коммит делает ведущий после проверки задачи.
- **Не запускайте `uv run check` целиком.** Только команды из шагов.
- Комментарии в конфигурации на русском, объясняют «почему».
- **Подменяется ровно один адрес — `/`.** `/plans`, `/login`, `/legal/*`, `/app/`, `/api`, `/webhook`, `/health` продолжают работать как работали. Это проверяется тестом.
- Существующие локации в `docker/nginx.conf` не переписываются: добавляется новая и переносится содержимое корневой в именованную.
- **Заголовки безопасности подключаются в каждой новой локации заново.** `add_header` внутри `location` заменяет весь унаследованный набор, а не дополняет его — об этом написано прямо в `docker/security-headers.conf`.

---

### Task 1: Подмена в nginx

**Files:**
- Modify: `docker/nginx.conf`
- Modify: `compose.yml`
- Create: `.gitignore` — запись для каталога `landing/` (если такого файла нет — создать)

**Interfaces:**
- Produces: каталог `/srv/landing` в контейнере nginx, переменная `LANDING_DIR` со значением по умолчанию `./landing`.

- [ ] **Step 1: Переписать корневую локацию**

В `docker/nginx.conf` заменить существующий блок `location / { … }` на три блока. Содержимое проксирования переезжает в именованную локацию без изменений:

```nginx
    # Свой лендинг развернувшего.
    #
    # Каталог монтируется томом только для чтения. Файла нет — try_files
    # уходит в @web, и главную отдаёт приложение. Переключателя «включить
    # своё» намеренно нет: наличие index.html и есть переключатель, а
    # настройка, которую надо не забыть выставить, однажды не выставляется.
    location = / {
        root /srv/landing;
        try_files /index.html @web;

        include /etc/nginx/snippets/security-headers.conf;
        add_header X-Frame-Options "DENY" always;
    }

    # Стили, скрипты и картинки своей страницы.
    location /landing/ {
        alias /srv/landing/;

        include /etc/nginx/snippets/security-headers.conf;
        add_header X-Frame-Options "DENY" always;
    }

    location / {
        set $web_upstream http://web:3000;
        proxy_pass $web_upstream$request_uri;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        include /etc/nginx/snippets/security-headers.conf;
        add_header X-Frame-Options "DENY" always;
    }

    location @web {
        set $web_upstream http://web:3000;
        proxy_pass $web_upstream$request_uri;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        include /etc/nginx/snippets/security-headers.conf;
        add_header X-Frame-Options "DENY" always;
    }
```

- [ ] **Step 2: Смонтировать каталог**

В `compose.yml` у сервиса `nginx` добавить:

```yaml
    volumes:
      # Пустой каталог — штатный лендинг. Только чтение: содержимое приносит
      # развернувший, менять его контейнер не должен.
      - ${LANDING_DIR:-./landing}:/srv/landing:ro
```

Если у сервиса уже есть `volumes`, добавьте строку к ним.

- [ ] **Step 3: Не тащить чужие файлы в репозиторий**

В `.gitignore` добавить:

```gitignore
# Своя главная страница развернувшего: его файлы, не наши.
/landing/
```

Каталог создаётся Docker'ом при первом запуске, если его нет.

- [ ] **Step 4: Проверить конфигурацию**

Run: `docker compose config --quiet`
Expected: без вывода — файл разобран.

Проверить сам nginx.conf можно только вместе с образом; это сделает ведущий при сборке. Синтаксис блоков сверьте глазами: `try_files` в `location = /` обязан ссылаться на `@web`, а не на `/index.html` во второй раз — иначе несуществующий файл даст 404 вместо приложения.

---

### Task 2: Документация

**Files:**
- Modify: `docs/deployment.md`
- Modify: `README.md`

**Interfaces:** ничего не появляется — описывается сделанное в Task 1.

- [ ] **Step 1: Написать раздел**

В `docs/deployment.md` добавьте раздел «Своя главная страница» (номер — следующий по порядку в файле, посмотрите последний). Он обязан отвечать на пять вопросов; без любого из них человек не сможет воспользоваться возможностью.

**Куда класть.** Каталог `./landing` рядом с `compose.yml`; путь меняется переменной `LANDING_DIR`. Внутри обязателен `index.html`, остальное — по желанию.

```bash
mkdir -p landing
cp -r моя-страница/* landing/
docker compose restart nginx
```

**Как ссылаться на ассеты.** Файлы каталога доступны по `/landing/…`: `landing/style.css` открывается как `/landing/style.css`. Пути вида `./style.css` тоже работают, потому что страница отдаётся с корня.

**Какие ссылки обязательны.** Без них человек не сможет купить:

| Адрес | Зачем |
|---|---|
| `/register` | Создать аккаунт |
| `/login` | Войти |
| `/plans` | Тарифы и покупка |
| `/legal/<slug>` | Заведённые юридические документы |
| `/app/` | MiniApp, если она нужна на странице |

**Откуда взять данные.** Два адреса открыты без входа, их можно запрашивать прямо из браузера, поэтому цены и правовые ссылки не обязаны быть переписанными руками:

```js
const plans = await (await fetch('/api/plans')).json()
const documents = await (await fetch('/api/legal?locale=ru')).json()
```

Приведите короткий рабочий пример `index.html` — заголовок, кнопка на `/register`, список тарифов из `/api/plans` и ссылки из `/api/legal`. Пример должен запускаться как есть.

**Чего нельзя.** Занимать `/api`, `/app`, `/webhook`, `/health` и любые пути приложения: подменяется ровно один адрес — `/`. Всё остальное продолжает вести в приложение, и файл с именем `plans` в каталоге ничего не изменит.

**Знак и цвета.** Бренд-набор лежит в `docs/design/logo`, правила — в `docs/design/repibot-brandbook.md`. Знак не поворачивают, спираль не замыкают, зазор между ядром и линией не закрывают.

**Как вернуть штатную главную.** Удалить `index.html` из каталога и перезапустить nginx.

- [ ] **Step 2: Упомянуть возможность в README**

В `README.md` добавьте одно-два предложения в абзац о развёртывании: главную можно заменить своей страницей, положив её в `./landing`, подробности — в `docs/deployment.md`. Остальной текст README не трогайте.

- [ ] **Step 3: Проверить ссылки**

Убедитесь, что якорь раздела, на который ссылается README, действительно существует в `docs/deployment.md` (заголовок с тем же текстом).

---

### Task 3: Проверка подмены

**Files:**
- Create: `frontend/apps/web/e2e/landing-probe/index.html`
- Create: `frontend/apps/web/e2e/custom-landing.spec.ts`
- Create: `frontend/apps/web/playwright.landing.config.ts`
- Create: `frontend/apps/web/e2e/landing-stack.ts`
- Modify: `frontend/apps/web/package.json` — **не редактируйте сами.** Скрипт `e2e:landing` добавит ведущий; сообщите ему точную строку, когда задача будет готова.

**Interfaces:**
- Produces: отдельный прогон Playwright, проверяющий подмену и возвращающий контур в исходное состояние.

**Почему отдельным прогоном.** Том монтируется при создании контейнера, поэтому проверить обе главные — штатную и чужую — в одном прогоне нельзя: между ними nginx надо пересоздать. Основной обход проверяет штатную; этот прогон пересоздаёт nginx с пробным каталогом, проверяет чужую и возвращает всё обратно.

- [ ] **Step 1: Написать пробную страницу**

`frontend/apps/web/e2e/landing-probe/index.html`:

```html
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <title>Пробная главная</title>
  </head>
  <body>
    <h1>Своя главная страница</h1>
    <p>Эту страницу отдал nginx из смонтированного каталога.</p>
    <a href="/plans">Тарифы</a>
    <a href="/register">Регистрация</a>
  </body>
</html>
```

- [ ] **Step 2: Написать подъём контура для этого прогона**

`frontend/apps/web/e2e/landing-stack.ts`:

```ts
/**
 * Пересоздаёт nginx со смонтированной пробной главной.
 *
 * Том монтируется при создании контейнера: подменить каталог у работающего
 * nginx нельзя, поэтому его пересоздают. После прогона контур возвращается
 * в исходное состояние — иначе следующий сквозной обход увидит вместо
 * главной пробную страницу и не объяснит почему.
 */

import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

const ROOT = resolve(__dirname, '../../../..')
const PROJECT = 'repibot-e2e'
const ENV_FILE = 'frontend/apps/web/e2e/stack.env'
const FILES = ['compose.yml', 'frontend/apps/web/e2e/compose.e2e.yml']
const PROBE_DIR = 'frontend/apps/web/e2e/landing-probe'

function compose(landingDir: string, ...args: string[]): void {
  const command = [
    'compose',
    '--project-name',
    PROJECT,
    '--env-file',
    ENV_FILE,
    ...FILES.flatMap((file) => ['--file', file]),
    '--profile',
    'dev',
    ...args,
  ]
  execFileSync('docker', command, {
    cwd: ROOT,
    stdio: 'inherit',
    env: { ...process.env, LANDING_DIR: landingDir },
  })
}

export function mountProbeLanding(): void {
  compose(PROBE_DIR, 'up', '-d', '--force-recreate', 'nginx')
}

export function restoreDefaultLanding(): void {
  compose('./landing', 'up', '-d', '--force-recreate', 'nginx')
}
```

- [ ] **Step 3: Написать конфигурацию и тест**

`frontend/apps/web/playwright.landing.config.ts`:

```ts
import { defineConfig } from '@playwright/test'

import { WEB_URL } from './e2e/stack'

/**
 * Прогон подмены главной. Контур должен быть уже поднят обычным способом:
 * здесь пересоздаётся только nginx.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: 'custom-landing.spec.ts',
  globalSetup: './e2e/landing-setup.ts',
  globalTeardown: './e2e/landing-teardown.ts',
  workers: 1,
  timeout: 60_000,
  use: { baseURL: WEB_URL, locale: 'ru-RU', trace: 'retain-on-failure' },
  reporter: [['list']],
})
```

`frontend/apps/web/e2e/landing-setup.ts`:

```ts
import { mountProbeLanding } from './landing-stack'

export default function globalSetup(): void {
  mountProbeLanding()
}
```

`frontend/apps/web/e2e/landing-teardown.ts`:

```ts
import { restoreDefaultLanding } from './landing-stack'

export default function globalTeardown(): void {
  restoreDefaultLanding()
}
```

`frontend/apps/web/e2e/custom-landing.spec.ts`:

```ts
import { expect, test } from '@playwright/test'

/**
 * Подменяется ровно один адрес.
 *
 * Проверяется не только то, что чужая страница появилась, но и то, что всё
 * остальное осталось на месте: подмена, уносящая с собой тарифы и вход,
 * никому не нужна.
 */

test('своя главная отдаётся вместо штатной', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Своя главная страница')
})

test('остальные адреса продолжают вести в приложение', async ({ page }) => {
  await page.goto('/plans')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  await page.goto('/login')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
})

test('публичное API отвечает по-прежнему', async ({ request }) => {
  const plans = await request.get('/api/plans')

  expect(plans.status()).toBe(200)
  expect(Array.isArray(await plans.json())).toBe(true)
})
```

- [ ] **Step 4: Сообщить ведущему строку скрипта**

Ведущий добавит в `frontend/apps/web/package.json`:

```json
    "e2e:landing": "playwright test --config playwright.landing.config.ts"
```

- [ ] **Step 5: Проверить типы и линтер**

Run: `cd frontend && pnpm --filter @repibot/web typecheck && pnpm exec biome check .`
Expected: без замечаний.

Сам прогон здесь не запускается: он пересоздаёт контейнеры и не укладывается в лимит времени задачи. Его выполнит ведущий.

---

## Готовность плана

После трёх задач развернувший может подменить главную своей страницей, зная из документации, куда её класть, какие ссылки обязательны и откуда взять цены; проверка убеждается, что подменился ровно один адрес.
