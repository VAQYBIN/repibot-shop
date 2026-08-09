import { AuthProvider, createQueryClient } from '@repibot/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { type RenderResult, render } from '@testing-library/react'
import { type ReactElement, type ReactNode, useEffect } from 'react'
import { vi } from 'vitest'

import { BrowserPreferencesProvider } from '@/lib/browser-preferences'

type HandlerResult = Response | unknown
type Handler = HandlerResult | ((request: Request) => HandlerResult | Promise<HandlerResult>)

interface StructuredResponse {
  status: number
  body: unknown
}

interface RenderWithProvidersOptions {
  handlers?: Record<string, Handler>
}

function isStructuredResponse(value: unknown): value is StructuredResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'status' in value &&
    typeof value.status === 'number' &&
    'body' in value
  )
}

function renderWithQueryClient(ui: ReactElement, retry: boolean): RenderResult {
  const queries = createQueryClient()
  queries.setDefaultOptions({ queries: { retry } })

  return render(
    <BrowserPreferencesProvider>
      <QueryClientProvider client={queries}>
        <AuthProvider baseUrl="http://api.test">{ui}</AuthProvider>
      </QueryClientProvider>
    </BrowserPreferencesProvider>,
  )
}

function RestoreFetch({ children, previous }: { children: ReactNode; previous: typeof fetch }) {
  useEffect(
    () => () => {
      globalThis.fetch = previous
    },
    [previous],
  )
  return children
}

/**
 * Обёртка страниц для тестов.
 *
 * Базовый URL здесь абсолютный, хотя в приложении он пустой: вне браузера
 * конструктор Request не принимает относительный адрес и упал бы раньше, чем
 * запрос дошёл до подменённого fetch.
 */
export function renderWithAuth(ui: ReactElement): RenderResult {
  return renderWithQueryClient(ui, true)
}

/**
 * Обёртка для страниц, которые читают API сразу после монтирования.
 *
 * Ответ привязан к pathname, поэтому тест описывает только нужные маршруты,
 * а случайный дополнительный запрос получает честный 404. Ошибки запросов не
 * повторяются: состояние должно доходить до страницы без задержки.
 */
export function renderWithProviders(
  ui: ReactElement,
  { handlers = {} }: RenderWithProvidersOptions = {},
): RenderResult {
  const previousFetch = globalThis.fetch
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      const handler = handlers[new URL(request.url).pathname]
      if (handler === undefined) return new Response(null, { status: 404 })

      const result = typeof handler === 'function' ? await handler(request) : handler
      if (result instanceof Response) return result
      if (isStructuredResponse(result)) {
        return result.body === undefined || result.status === 204
          ? new Response(null, { status: result.status })
          : Response.json(result.body, { status: result.status })
      }
      return Response.json(result)
    }),
  )

  return renderWithQueryClient(<RestoreFetch previous={previousFetch}>{ui}</RestoreFetch>, false)
}
