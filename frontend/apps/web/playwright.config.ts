import { defineConfig } from '@playwright/test'

import { WEB_URL } from './e2e/stack'

/**
 * Сквозные тесты идут по всему стеку сразу.
 *
 * `next start` вместо стека не годится: кабинет живёт на refresh-cookie и
 * относительных путях `/api`, а их сводит воедино nginx. Стек поднимает
 * globalSetup — см. `e2e/stack.ts`.
 */
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/stack.ts',
  // База, Valkey, Mailpit и FakePanel общие для всего изолированного стека.
  // Один worker делает порядок работы с этим состоянием воспроизводимым.
  workers: 1,
  // Сценарий ждёт письмо через очередь: тридцати секунд на тест мало.
  timeout: 90_000,
  use: {
    baseURL: WEB_URL,
    // Язык интерфейса выбирается по настройкам браузера, а Playwright по
    // умолчанию представляется en-US. Подписи в тестах русские — значит и
    // браузер должен быть русским, иначе селекторы не найдут ничего.
    locale: 'ru-RU',
    trace: 'retain-on-failure',
  },
  reporter: [['list'], ['html', { open: 'never' }]],
})
