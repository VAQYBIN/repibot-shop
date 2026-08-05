import { AuthProvider, createQueryClient } from '@repibot/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { type RenderResult, render } from '@testing-library/react'
import type { ReactElement } from 'react'

/**
 * Обёртка страниц для тестов.
 *
 * Базовый URL здесь абсолютный, хотя в приложении он пустой: вне браузера
 * конструктор Request не принимает относительный адрес и упал бы раньше, чем
 * запрос дошёл до подменённого fetch.
 */
export function renderWithAuth(ui: ReactElement): RenderResult {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider baseUrl="http://api.test">{ui}</AuthProvider>
    </QueryClientProvider>,
  )
}
