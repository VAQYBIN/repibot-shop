import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, type Page, test } from '@playwright/test'

import { waitForLink } from './mailpit'
import { PANEL_URL, resetRegistrationRateLimit, seed } from './seed'
import { MAILPIT_URL } from './stack'

const PASSWORD = 'надёжный пароль для подписки'
const VERIFY_LINK = /https?:\/\/\S+\/verify-email\S+/

test.beforeAll(() => resetRegistrationRateLimit())

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

async function registerAndSignIn(page: Page, email: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click()
  await expect(page.getByText(/Проверьте почту/i)).toBeVisible()

  const link = await waitForLink(MAILPIT_URL, email, VERIFY_LINK)
  await page.goto(link)
  await expect(page).toHaveURL(/\/account/)
}

test('витрина показывает засеянные тарифы', async ({ page }) => {
  await page.goto('/plans')

  await expect(page.getByRole('heading', { name: 'Месяц' })).toBeVisible()
  await expect(page.getByText('299 ₽')).toBeVisible()
  await captureVisualVariants(page, 'plans')
})

test('кабинет объясняет отсутствие подписки', async ({ page }) => {
  await registerAndSignIn(page, 'subscription-empty@example.com')
  await page.goto('/account/subscription')

  await expect(page.getByText('Подписки пока нет')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Устройства' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Трафик' })).toHaveCount(0)
})

test('активная подписка показывает доступ, трафик и позволяет отвязать устройство', async ({
  page,
  request,
}) => {
  const email = 'subscription-active@example.com'
  await registerAndSignIn(page, email)

  const panelResponse = await request.post(`${PANEL_URL}/__seed/user`, {
    data: {
      username: 'rp_e2e_subscription',
      expireAt: '2099-01-01T00:00:00Z',
      device: {
        hwid: 'phone-e2e',
        platform: 'Android',
        osVersion: '15',
        deviceModel: 'Pixel 9',
      },
      traffic: {
        usedTrafficBytes: 2_048,
        lifetimeUsedTrafficBytes: 8_192,
        days: { '2026-08-07': 512, '2026-08-08': 1_536 },
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

  await page.goto('/account/subscription')

  await expect(page.getByRole('link', { name: panelUser.subscriptionUrl })).toBeVisible()
  await expect(page.getByText('Pixel 9')).toBeVisible()
  const traffic = page.getByRole('region', { name: 'Трафик' })
  await expect(traffic.getByText('2 КБ / 100 ГБ', { exact: true })).toBeVisible()
  await expect(traffic.getByText('За последние дни', { exact: true })).toBeVisible()
  await expect(traffic.getByText('7 авг. 2026 г.', { exact: true })).toBeVisible()
  await expect(traffic.getByText('512 Б', { exact: true })).toBeVisible()
  await expect(traffic.getByText('8 авг. 2026 г.', { exact: true })).toBeVisible()
  await expect(traffic.getByText('1,5 КБ', { exact: true })).toBeVisible()
  await captureVisualVariants(page, 'subscription')

  await page.getByRole('button', { name: 'Отвязать Pixel 9', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('Доступ на этом устройстве прекратится.')
  await dialog.getByRole('button', { name: 'Отвязать', exact: true }).click()

  await expect(page.getByText('Устройств пока нет')).toBeVisible()
  await expect(page.getByText('Pixel 9')).toHaveCount(0)
})
