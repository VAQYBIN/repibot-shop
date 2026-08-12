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
