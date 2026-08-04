import { expect, test } from '@playwright/test'

/**
 * Единственный сквозной сценарий этого подпроекта: страница собирается,
 * отдаётся и переключает тему. Сценарии регистрации и покупки появятся,
 * когда появятся регистрация и покупка.
 */
test('главная открывается и переключает тему', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByText('Магазин ещё готовится')).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')

  await page.getByRole('button', { name: 'Тёмная тема' }).click()

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('страница юридического документа не отдаёт 404', async ({ page }) => {
  const response = await page.goto('/legal/terms')

  expect(response?.status()).toBe(200)
  await expect(page.getByText('Документ: terms')).toBeVisible()
})
