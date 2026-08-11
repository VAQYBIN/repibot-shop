import { AuthProvider } from '@repibot/core'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type RenderResult, render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { type Mock, vi } from 'vitest'

import { tokenStore } from './api'

/** Ответ `/api/me` для тестов. Поля совпадают со схемой `MeResponse`. */
export const PROFILE = {
  id: 1,
  email: null,
  email_verified: false,
  telegram_username: 'anya',
  name: 'Аня',
  language: 'ru',
  role: 'user',
  referral_code: 'RP-ABC123',
  has_password: false,
  has_telegram: true,
  passkey_count: 0,
} as const

/**
 * Подмена fetch. Клиент API берёт `globalThis.fetch` в момент создания, поэтому
 * подмена ставится до отрисовки провайдера.
 */
export function stubFetch(handler: (request: Request) => Response): Mock {
  const mock = vi.fn(async (request: Request) => handler(request))
  vi.stubGlobal('fetch', mock)
  return mock
}

/**
 * Запросы в тестах не повторяются: ошибка должна доходить до экрана сразу.
 * Срок годности снимка задаёт тест — в приложении он равен 30 секундам.
 */
export function renderWithProviders(ui: ReactNode, staleTime = 0): RenderResult {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime } } })
  return render(
    <QueryClientProvider client={queries}>
      {/* Адрес абсолютный: jsdom берёт Request из Node, а тот относительный
          путь разобрать не умеет — в браузере он разрешается сам. */}
      <AuthProvider baseUrl="https://miniapp.test" store={tokenStore}>
        {ui}
      </AuthProvider>
    </QueryClientProvider>,
  )
}

/** По умолчанию jsdom сообщает en-US, а тексты проверяются по-русски. */
export function withRussianLocale(): void {
  vi.stubGlobal('navigator', { ...navigator, languages: ['ru-RU'] })
}
