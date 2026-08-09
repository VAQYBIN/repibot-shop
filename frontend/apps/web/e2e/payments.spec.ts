import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, type Page, test } from '@playwright/test'

import { waitForLink } from './mailpit'
import { grantE2eAdmin, resetRegistrationRateLimit } from './seed'
import { MAILPIT_URL, WEB_URL } from './stack'

const PASSWORD = 'надёжный пароль для платежного сценария'
const VERIFY_LINK = /https?:\/\/\S+\/verify-email\S+/
const FAKE_YOOKASSA_URL = process.env.E2E_YOOKASSA_URL ?? 'http://127.0.0.1:3002'

test.beforeAll(() => resetRegistrationRateLimit())

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}@example.com`
}

async function registerAndSignIn(page: Page, email: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click()
  const link = await waitForLink(MAILPIT_URL, email, VERIFY_LINK)
  await page.goto(link)
  await expect(page).toHaveURL(/\/account/)
}

async function captureVisualVariants(page: Page, surface: string): Promise<void> {
  const configured = process.env.E2E_VISUAL_DIR
  if (configured === undefined) return

  const output = resolve(configured)
  mkdirSync(output, { recursive: true })
  const variants = [
    { name: 'desktop-light', width: 1440, height: 1000, colorScheme: 'light' },
    { name: 'desktop-dark', width: 1440, height: 1000, colorScheme: 'dark' },
    { name: 'narrow-light', width: 390, height: 844, colorScheme: 'light' },
    { name: 'narrow-dark', width: 390, height: 844, colorScheme: 'dark' },
  ] as const

  for (const variant of variants) {
    await page.setViewportSize({ width: variant.width, height: variant.height })
    await page.emulateMedia({ colorScheme: variant.colorScheme })
    await page.waitForFunction(
      (theme) => document.documentElement.dataset.theme === theme,
      variant.colorScheme,
    )
    await page.screenshot({
      path: resolve(output, `${surface}-${variant.name}.png`),
      fullPage: true,
      animations: 'disabled',
    })
  }
}

async function createCardOrder(page: Page): Promise<string> {
  await page.goto('/account/payments')
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/me/orders') && response.request().method() === 'POST',
    ),
    page.getByRole('button', { name: 'Оплатить картой' }).click(),
  ])
  const latest = await page.request.get(`${FAKE_YOOKASSA_URL}/__e2e/payments/latest`)
  expect(latest.ok()).toBe(true)
  return (await latest.json()).id as string
}

async function setProviderStatus(page: Page, paymentId: string, status: 'succeeded' | 'canceled') {
  const updated = await page.request.post(
    `${FAKE_YOOKASSA_URL}/__e2e/payments/${paymentId}/status`,
    {
      data: { status },
    },
  )
  expect(updated.ok()).toBe(true)
  const webhook = await page.request.post(`${WEB_URL}/webhook/yookassa`, {
    data: { object: { id: paymentId, status: 'untrusted' } },
  })
  expect(webhook.status()).toBe(204)
}

test('оплата картой проверяется по провайдеру и выдаёт подписку один раз', async ({ page }) => {
  await registerAndSignIn(page, uniqueEmail('payment-success'))
  const paymentId = await createCardOrder(page)

  await setProviderStatus(page, paymentId, 'succeeded')
  await page.reload()

  await expect(page.getByText('Оплачен', { exact: true })).toBeVisible()
  await page.goto('/account/subscription')
  await expect(page.getByText('Месяц', { exact: true })).toBeVisible()
})

test('неуспешный платёж не выдаёт подписку', async ({ page }) => {
  await registerAndSignIn(page, uniqueEmail('payment-failure'))
  const paymentId = await createCardOrder(page)

  await setProviderStatus(page, paymentId, 'canceled')
  await page.reload()

  // Провайдерская отмена остаётся ожидающим заказом до TTL: пользователь может
  // повторить оплату, но право не выдаётся без подтверждённого success.
  await expect(page.getByText('Ожидает оплаты', { exact: true })).toBeVisible()
  await page.goto('/account/subscription')
  await expect(page.getByText('Подписки пока нет')).toBeVisible()
})

test('admin payments остаётся server-gated и рендерится во всех visual-вариантах', async ({
  page,
}) => {
  const email = uniqueEmail('payment-admin')
  await registerAndSignIn(page, email)
  grantE2eAdmin(email)

  await page.goto('/admin/payments')
  await expect(page.getByRole('heading', { name: 'Платежи и корректировки' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Отметить возврат' })).toBeDisabled()
  await captureVisualVariants(page, 'admin-payments')
})
