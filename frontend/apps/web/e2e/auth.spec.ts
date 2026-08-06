import { expect, type Page, test } from '@playwright/test'

import { waitForLink } from './mailpit'
import { MAILPIT_URL } from './stack'

/**
 * Сквозные сценарии входа.
 *
 * Проверяется путь целиком: браузер → nginx → API → очередь → письмо в Mailpit
 * → ссылка обратно в браузер. Каждый шаг по отдельности покрыт тестами уровнем
 * ниже; здесь важно, что они соединены.
 *
 * Подписи берутся из словаря `@repibot/core` дословно и с `exact`:
 * приблизительное совпадение задевает соседей — «Пароль» находит и «Показать
 * пароль», «Войти» — и «Войти по ключу», — а строгий режим Playwright на двух
 * найденных элементах падает.
 */

const PASSWORD = 'совершенно обычный пароль'
const OTHER_PASSWORD = 'другой совершенно обычный пароль'

const VERIFY_LINK = /https?:\/\/\S+\/verify-email\S+/
const RESET_LINK = /https?:\/\/\S+\/reset-password\S+/

/**
 * Адрес на каждый прогон свой: аккаунт от прошлого запуска занял бы почту.
 *
 * Домен именно `example.com`: зарезервированные зоны вроде `.test` и `.local`
 * отвергает проверка адреса на бэкенде. Наружу письмо всё равно не уходит —
 * SMTP стека смотрит в Mailpit.
 */
function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}@example.com`
}

async function registerAndVerify(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click()

  await expect(page.getByText(/Проверьте почту/i)).toBeVisible()

  const link = await waitForLink(MAILPIT_URL, email, VERIFY_LINK)
  await page.goto(link)

  await expect(page).toHaveURL(/\/account/)
}

async function signOut(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Выйти' }).click()
  await expect(page).toHaveURL(/\/login/)
}

test('регистрация, подтверждение почты и вход', async ({ page }) => {
  const email = uniqueEmail('user')
  await registerAndVerify(page, email, PASSWORD)

  await expect(page.getByText(email)).toBeVisible()
  await expect(page.getByText('Адрес подтверждён')).toBeVisible()

  // Вход проверяется отдельно от подтверждения: ссылка из письма выдаёт сессию
  // сама, и без этого шага пароль оставался бы непроверенным.
  await signOut(page)
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()

  await expect(page).toHaveURL(/\/account/)
  await expect(page.getByText(email)).toBeVisible()
})

test('кабинет закрыт без входа', async ({ page }) => {
  await page.goto('/account')

  await expect(page).toHaveURL(/\/login/)
})

test('сброс пароля пускает с новым паролем', async ({ page }) => {
  const email = uniqueEmail('reset')
  await registerAndVerify(page, email, PASSWORD)
  await signOut(page)

  await page.goto('/forgot-password')
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByRole('button', { name: 'Отправить ссылку' }).click()
  await expect(page.getByText(/письмо уже отправлено/i)).toBeVisible()

  const link = await waitForLink(MAILPIT_URL, email, RESET_LINK)
  await page.goto(link)
  await page.getByLabel('Новый пароль', { exact: true }).fill(OTHER_PASSWORD)
  await page.getByRole('button', { name: 'Сохранить пароль' }).click()

  await expect(page).toHaveURL(/\/account/)

  // Прежний пароль после сброса не работает — иначе сброс не защищает от угона.
  await signOut(page)
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()

  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
})

test('отзыв сессии обрывает доступ', async ({ page, browser }) => {
  const email = uniqueEmail('revoke')
  await registerAndVerify(page, email, PASSWORD)

  // Второй контекст — это второе устройство: своя cookie, своя сессия.
  const second = await browser.newContext()
  const secondPage = await second.newPage()
  await secondPage.goto('/login')
  await secondPage.getByLabel('Почта', { exact: true }).fill(email)
  await secondPage.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await secondPage.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(secondPage).toHaveURL(/\/account/)

  await page.goto('/account/security')
  // Единственная кнопка «Отозвать» в списке — у чужого устройства: у текущего
  // её нет вовсе. Вторая такая кнопка появляется уже в окне подтверждения.
  await page.getByRole('button', { name: 'Отозвать', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Отозвать', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Отозвать', exact: true })).toHaveCount(0)

  await secondPage.goto('/account')
  await expect(secondPage).toHaveURL(/\/login/)

  await second.close()
})
