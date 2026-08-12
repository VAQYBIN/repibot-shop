import { expect, test } from '@playwright/test'

/**
 * Подменяется ровно один адрес.
 *
 * Проверяется не только то, что чужая страница появилась, но и то, что всё
 * остальное осталось на месте: подмена, уносящая с собой тарифы и вход,
 * никому не нужна.
 *
 * Прогон отдельный — см. `playwright.landing.config.ts`: пробный каталог
 * монтируется при создании контейнера, и в общем обходе места ему нет.
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
