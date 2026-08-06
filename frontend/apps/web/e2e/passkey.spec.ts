import { expect, type Page, test } from '@playwright/test'

import { waitForLink } from './mailpit'
import { MAILPIT_URL } from './stack'

/**
 * Сквозные сценарии входа по ключу доступа.
 *
 * Настоящего аутентификатора в CI нет, но проверять здесь нужно не криптографию
 * — её покрывают тесты уровнем ниже. Непроверенным без сквозного прогона
 * остаётся стык браузера и сервера: RP ID выводится из `PUBLIC_WEB_URL`, а
 * origin браузер подставляет сам, и расхождение этих двух значений видно только
 * так. В стеке сквозных тестов адрес — `http://localhost:8081`, то есть RP ID
 * `localhost`: безопасный контекст без TLS, ключи на нём заводятся.
 *
 * Подписи берутся из словаря `@repibot/core` дословно и с `exact`: шаблон вроде
 * /пароль/i совпал бы заодно с кнопкой «Показать пароль» и упал бы на строгом
 * режиме Playwright.
 *
 * Браузерный вход через Telegram сюда не входит: он уходит на
 * `oauth.telegram.org`, поднять который в стеке нельзя. Его проверяют тесты
 * роутера на мокнутом JWKS и ручной пункт критериев приёмки.
 */

const PASSWORD = 'совершенно обычный пароль'

const VERIFY_LINK = /https?:\/\/\S+\/verify-email\S+/

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}@example.com`
}

/**
 * Виртуальный аутентификатор Chromium через CDP.
 *
 * `hasResidentKey` обязателен: сервер просит discoverable-ключ, чтобы на экране
 * входа не спрашивать почту, и без резидентной записи вход по ключу не начался
 * бы вовсе. `isUserVerified` вместе с `automaticPresenceSimulation` заменяют
 * отпечаток и касание — подтверждать в тесте некому.
 *
 * Аутентификатор живёт в контексте страницы, а контекст у каждого теста свой:
 * ключ одного сценария в другой не протекает.
 */
async function addVirtualAuthenticator(page: Page): Promise<void> {
  const session = await page.context().newCDPSession(page)
  await session.send('WebAuthn.enable')
  await session.send('WebAuthn.addVirtualAuthenticator', {
    options: {
      protocol: 'ctap2',
      transport: 'internal',
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  })
}

async function registerAndVerify(page: Page, email: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click()

  const link = await waitForLink(MAILPIT_URL, email, VERIFY_LINK)
  await page.goto(link)

  await expect(page).toHaveURL(/\/account/)
}

async function addPasskey(page: Page, name: string): Promise<void> {
  await page.goto('/account/security')
  await page.getByLabel('Название ключа', { exact: true }).fill(name)
  await page.getByRole('button', { name: 'Добавить ключ', exact: true }).click()

  await expect(page.getByText(name, { exact: true })).toBeVisible()
}

async function signOut(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Выйти', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
}

test('ключ доступа заводится в кабинете и пускает в него без пароля', async ({ page }) => {
  const email = uniqueEmail('passkey')
  await addVirtualAuthenticator(page)
  await registerAndVerify(page, email)

  await addPasskey(page, 'Тестовый ключ')
  await signOut(page)

  await page.getByRole('button', { name: 'Войти по ключу', exact: true }).click()

  // Ни почты, ни пароля на этом пути не вводилось: аккаунт опознан по самому
  // ключу, значит RP ID сервера и origin браузера сошлись.
  await expect(page).toHaveURL(/\/account/)
  await expect(page.getByText(email)).toBeVisible()
})

test('снятый ключ пропадает из списка и больше не пускает', async ({ page }) => {
  const email = uniqueEmail('key-off')
  await addVirtualAuthenticator(page)
  await registerAndVerify(page, email)

  await addPasskey(page, 'Единственный')

  // Единственный способ входа снять нельзя, но у этого аккаунта есть ещё и
  // пароль — поэтому ключ снимается. Отказ по правилу «последний снять нельзя»
  // проверяют тесты сервиса: аккаунта без пароля через веб не завести.
  await page.getByRole('button', { name: 'Удалить', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click()

  // Пустой список, а не отсутствие ошибки: у Next.js есть собственный
  // `role="alert"` для объявления смены страницы, и считать алерты на этой
  // странице бессмысленно.
  await expect(page.getByText('Единственный', { exact: true })).toBeHidden()
  await expect(page.getByText('Ключей пока нет')).toBeVisible()

  await signOut(page)

  // Ключ остался в аутентификаторе и по-прежнему подписывает — не пускать его
  // должен сервер. Иначе снятие ключа было бы косметикой.
  await page.getByRole('button', { name: 'Войти по ключу', exact: true }).click()

  await expect(page.getByText('Неверная почта или пароль')).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
})
