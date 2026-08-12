import { expect, test } from '@playwright/test'

/**
 * Самая короткая проверка витрины: главная и документ собираются на сервере
 * и отдаются целиком. Обе страницы берут данные из API в момент запроса,
 * поэтому пустая разметка здесь означала бы не пустую базу, а разорванную
 * связь между вебом и API — то, чего не увидит ни один тест компонента.
 */
test('главная показывает тарифы и переключает тему', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  // Цена приходит из того же /api/plans, что и в кабинете, и попадает в
  // разметку на сервере: посев заводит тариф «Месяц».
  await expect(page.getByText('Месяц').first()).toBeVisible()

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Тёмная тема' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('страница юридического документа показывает опубликованный текст', async ({ page }) => {
  const response = await page.goto('/legal/terms')

  expect(response?.status()).toBe(200)
  await expect(
    page.getByRole('heading', { level: 1, name: 'Пользовательское соглашение' }),
  ).toBeVisible()
  // Заголовок раздела приходит из Markdown, отрисованного и очищенного на
  // бэкенде: если бы разметка не дошла, здесь остался бы простой текст.
  // Имя обязательно — заголовки второго уровня есть и в подвале.
  await expect(page.getByRole('heading', { level: 2, name: 'Общие положения' })).toBeVisible()
})

test('незаведённый документ отвечает «не найдено»', async ({ page }) => {
  const response = await page.goto('/legal/nothing-here')

  expect(response?.status()).toBe(404)
})
