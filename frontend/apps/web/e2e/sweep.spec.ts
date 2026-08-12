import { expect, type Page, test } from '@playwright/test'

import { waitForLink } from './mailpit'
import {
  grantE2eAdmin,
  PANEL_URL,
  resetRegistrationRateLimit,
  seed,
  seedTelegramUser,
} from './seed'
import { MAILPIT_URL } from './stack'
import { signInitData } from './telegram'

/**
 * Сквозной обход всех экранов проекта в обеих темах.
 *
 * Ни один тест компонента не собирает страницу в настоящем браузере — этот
 * обход единственный, кто проверяет три вещи разом на каждом экране: нет
 * ошибок в консоли, разметка не уехала вбок и страница действительно
 * отрисовалась (а не пустой каркас после упавшего запроса — заголовок
 * первого уровня тому свидетель).
 */

/** Экраны, доступные без входа. */
const PUBLIC = ['/', '/plans', '/legal/terms', '/login', '/register', '/forgot-password']

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

/** Семь экранов MiniApp — переделка здесь глубже всего. */
const MINIAPP = [
  '/app/',
  '/app/subscription',
  '/app/devices',
  '/app/payments',
  '/app/profile',
  '/app/support',
  '/app/winback',
]

const THEMES = ['light', 'dark'] as const

const PASSWORD = 'обход по всем экранам сразу'
const VERIFY_LINK = /https?:\/\/\S+\/verify-email\S+/

/** Адрес на каждый прогон свой: аккаунт от прошлого запуска занял бы почту. */
function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}@example.com`
}

/** Тот же способ входа, что в auth.spec.ts: регистрация и переход по ссылке из письма. */
async function registerAndVerify(page: Page, email: string): Promise<void> {
  // Регистраций разрешено пять в час на адрес, а обход заводит по человеку на
  // каждый набор — и все с одного адреса. Счётчик сбрасывается перед каждой,
  // тем же способом, что в payments.spec.ts: иначе половина наборов падает
  // не на своём предмете, а на защите от перебора.
  resetRegistrationRateLimit()

  await page.goto('/register')
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click()
  await expect(page.getByText(/Проверьте почту/i)).toBeVisible()

  const link = await waitForLink(MAILPIT_URL, email, VERIFY_LINK)
  await page.goto(link)
  await expect(page).toHaveURL(/\/account/)
}

/**
 * Слушатель ставится один раз на тест, а не на каждый переход: несколько
 * слушателей на одной странице продолжают писать в свои старые массивы и
 * ловят события чужих, более поздних экранов — сообщение об отказавшем
 * запросе печатается в консоль асинхронно и почти всегда опаздывает к
 * проверке того экрана, который его вызвал.
 */
function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  return errors
}

async function visit(page: Page, path: string, errors: string[]): Promise<void> {
  errors.length = 0
  await page.goto(path)
  await assertScreenHealthy(page, path, errors)
}

/** Три проверки, общие для goto- и click-навигации: их не два места, а одно. */
async function assertScreenHealthy(page: Page, label: string, errors: string[]): Promise<void> {
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

  // Разметка рисуется раньше, чем разрешаются все запросы экрана, а браузер
  // печатает сообщение об отказавшем запросе в консоль уже после ответа.
  // Без этой паузы такое сообщение достаётся проверке следующего, а не
  // текущего экрана.
  await page.waitForLoadState('networkidle')

  const overflow = await page.evaluate(() => {
    const root = document.scrollingElement
    return root === null ? 0 : root.scrollWidth - root.clientWidth
  })
  expect(overflow, `${label} уехала вбок на ${overflow}px`).toBeLessThanOrEqual(1)

  expect(errors, `${label}: ошибки в консоли`).toEqual([])
}

async function setTheme(page: Page, theme: string): Promise<void> {
  await page.addInitScript((value) => {
    // Тема ставится до первой отрисовки: иначе первый кадр всегда светлый,
    // и тёмная половина обхода проверяла бы светлую разметку.
    document.documentElement.dataset.theme = value
  }, theme)
}

for (const theme of THEMES) {
  test(`публичные экраны, тема ${theme}`, async ({ page }) => {
    const errors = trackConsoleErrors(page)
    await setTheme(page, theme)
    for (const path of PUBLIC) await visit(page, path, errors)
  })
}

for (const theme of THEMES) {
  test(`закрытые экраны кабинета, тема ${theme}`, async ({ page }) => {
    const errors = trackConsoleErrors(page)
    await setTheme(page, theme)
    await registerAndVerify(page, uniqueEmail(`sweep-private-${theme}`))
    for (const path of PRIVATE) await visit(page, path, errors)
  })
}

for (const theme of THEMES) {
  test(`экраны админки, тема ${theme}`, async ({ page, request }) => {
    const errors = trackConsoleErrors(page)
    await setTheme(page, theme)

    const email = uniqueEmail(`sweep-admin-${theme}`)
    await registerAndVerify(page, email)
    grantE2eAdmin(email)

    // Без настоящей подписки карточка своего же сотрудника в админке отвечает
    // на запрос устройств `subscription_missing` (404): это ожидаемое,
    // обработанное состояние (блок "Устройства" показывает alert с кнопкой
    // "Повторить"), но браузер всё равно печатает "Failed to load resource"
    // в консоль для любого неуспешного fetch — независимо от того, что
    // приложение отобразило ошибку аккуратно. Сеяный панельный пользователь с
    // устройством убирает этот структурный шум и заодно проверяет разметку
    // блока подписки/устройств с настоящими данными — а не только пустое
    // состояние.
    const panelResponse = await request.post(`${PANEL_URL}/__seed/user`, {
      data: {
        username: `rp_e2e_sweep_${theme}`,
        expireAt: '2099-01-01T00:00:00Z',
        device: {
          hwid: `sweep-admin-${theme}`,
          platform: 'Android',
          osVersion: '15',
          deviceModel: 'Pixel 9',
        },
      },
    })
    expect(panelResponse.ok()).toBe(true)
    const panelUser = (await panelResponse.json()).response as {
      id: number
      shortUuid: string
      subscriptionUrl: string
    }
    seed({
      email,
      panelId: panelUser.id,
      panelShortUuid: panelUser.shortUuid,
      subscriptionUrl: panelUser.subscriptionUrl,
    })

    // Перезагрузка теряет access-токен и вызывает refresh: без неё сотрудник
    // ходит по /admin со старой ролью из токена, а не из базы.
    await page.reload()
    await expect(page).toHaveURL(/\/account/)

    for (const path of ADMIN) await visit(page, path, errors)

    // /admin/users/[id] открывается переходом из списка, а не по адресу:
    // номер человека в контуре заранее не известен. Список сортирован по
    // убыванию id, и аккаунт самого сотрудника — последний зарегистрированный
    // в этом прогоне, поэтому он же первая строка.
    errors.length = 0
    await page.goto('/admin/users')
    await page.getByRole('table').getByRole('link').first().click()
    await expect(page).toHaveURL(/\/admin\/users\/\d+/)
    await assertScreenHealthy(page, '/admin/users/[id]', errors)
  })
}

for (const theme of THEMES) {
  test(`экраны MiniApp, тема ${theme}`, async ({ page }) => {
    const errors = trackConsoleErrors(page)

    // Свой номер Телеграма на тему: параллельного пересечения тем нет (один
    // worker), но раздельные номера честнее одного переиспользуемого.
    const telegramId = 910_000_000 + (theme === 'light' ? 1 : 2)
    const username = `sweep_${theme}`
    seedTelegramUser(telegramId, username)
    const initData = signInitData({ id: telegramId, username })

    // MiniApp живёт только на телефонном экране — проверять его на ширине
    // ноутбука бессмысленно.
    await page.setViewportSize({ width: 390, height: 844 })

    // Тему MiniApp задаёт не наш `data-theme`, а клиент Телеграма через
    // `colorScheme` — приложение читает его и ставит атрибут само. Оставить
    // здесь постоянное `light` значило бы прогнать тёмную половину обхода
    // по светлой разметке и ничего в ней не проверить.
    await page.addInitScript(
      ({ data, scheme }) => {
        const noop = () => undefined
        window.Telegram = {
          WebApp: {
            initData: data,
            initDataUnsafe: { user: { language_code: 'ru' } },
            colorScheme: scheme,
            ready: noop,
            expand: noop,
            openLink: noop,
            openTelegramLink: noop,
            onEvent: noop,
            offEvent: noop,
            MainButton: {
              setText: noop,
              show: noop,
              hide: noop,
              enable: noop,
              disable: noop,
              showProgress: noop,
              hideProgress: noop,
              onClick: noop,
              offClick: noop,
            },
            HapticFeedback: { notificationOccurred: noop, impactOccurred: noop },
          },
        }
      },
      { data: initData, scheme: theme },
    )

    for (const path of MINIAPP) await visit(page, path, errors)
  })
}
