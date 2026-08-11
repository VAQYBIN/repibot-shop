import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/hooks'
import { createTokenStore } from '../auth/store'
import { useNotificationSettings, useUpdateNotificationSettings } from './hooks'

const ENABLED = { marketing_enabled: true } as const
const DISABLED = { marketing_enabled: false } as const

/** Обёртка повторяет схему `subscription/hooks.test.tsx`: клиент API один и тот же. */
function createWrapper(staleTime = 0) {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime } } })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queries}>
        <AuthProvider baseUrl="https://api.test" store={createTokenStore()}>
          {children}
        </AuthProvider>
      </QueryClientProvider>
    )
  }

  return { queries, Wrapper }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('хуки согласия на новости', () => {
  it('читает текущее согласие', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json(ENABLED))
    vi.stubGlobal('fetch', fetchMock)
    const { Wrapper } = createWrapper()

    const { result } = renderHook(() => useNotificationSettings(), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.data).toEqual(ENABLED))
    const request = fetchMock.mock.calls[0]?.[0]
    expect(request?.url).toBe('https://api.test/api/me/notifications')
    expect(request?.method).toBe('GET')
  })

  it('отписка уезжает PATCH и сразу ложится в кэш', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json(DISABLED))
    vi.stubGlobal('fetch', fetchMock)
    const { queries, Wrapper } = createWrapper()
    const { result } = renderHook(() => useUpdateNotificationSettings(), { wrapper: Wrapper })

    await result.current.mutateAsync(false)

    const request = fetchMock.mock.calls[0]?.[0]
    expect(request).toBeInstanceOf(Request)
    if (!request) throw new Error('не отправлен запрос настроек уведомлений')
    expect(request.url).toBe('https://api.test/api/me/notifications')
    expect(request.method).toBe('PATCH')
    await expect(request.json()).resolves.toEqual(DISABLED)
    // Второй запрос за состоянием ничего не уточнит: сервер уже вернул его.
    expect(queries.getQueryData(['notification-settings'])).toEqual(DISABLED)
  })
})
