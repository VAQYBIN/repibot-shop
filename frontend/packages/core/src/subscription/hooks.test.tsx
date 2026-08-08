import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/hooks'
import { createTokenStore } from '../auth/store'
import {
  useActivateTrial,
  useDevices,
  usePlans,
  useSubscription,
  useTraffic,
  useUnlinkDevice,
} from './hooks'

const ACTIVE = {
  subscription: {
    plan_code: 'month',
    plan_name: { ru: 'Месяц', en: 'Month' },
    status: 'active',
    started_at: '2026-08-06T12:00:00Z',
    expires_at: '2026-09-05T12:00:00Z',
    subscription_url: 'https://panel.example.org/sub/abc',
    traffic_limit_bytes: 0,
    hwid_device_limit: 3,
  },
  trial_available: false,
} as const

const PENDING = {
  ...ACTIVE,
  subscription: { ...ACTIVE.subscription, status: 'pending_provision', subscription_url: null },
} as const

const PLANS = [
  {
    id: 1,
    code: 'month',
    name: { ru: 'Месяц', en: 'Month' },
    description: null,
    duration_days: 30,
    price_rub: '299.00',
    price_stars: 199,
    traffic_limit_bytes: 0,
    hwid_device_limit: 3,
    is_trial: false,
  },
] as const

const DEVICES = { devices: [], limit: 3, used: 0 } as const
const TRAFFIC = { used_bytes: 1024, lifetime_bytes: 4096, limit_bytes: 0, days: [] } as const

function createWrapper() {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } })

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
  vi.useRealTimers()
})

describe('хуки подписки', () => {
  it('читает все состояния по точным endpoint и query key', async () => {
    const fetchMock = vi.fn(async (request: Request) => {
      switch (new URL(request.url).pathname) {
        case '/api/plans':
          return Response.json(PLANS)
        case '/api/me/subscription':
          return Response.json(ACTIVE)
        case '/api/me/devices':
          return Response.json(DEVICES)
        case '/api/me/traffic':
          return Response.json(TRAFFIC)
        default:
          return new Response(null, { status: 404 })
      }
    })
    vi.stubGlobal('fetch', fetchMock)
    const { queries, Wrapper } = createWrapper()

    const { result } = renderHook(
      () => ({
        plans: usePlans(),
        subscription: useSubscription(),
        devices: useDevices(),
        traffic: useTraffic(),
      }),
      { wrapper: Wrapper },
    )

    await waitFor(() => {
      expect(result.current.plans.isSuccess).toBe(true)
      expect(result.current.subscription.isSuccess).toBe(true)
      expect(result.current.devices.isSuccess).toBe(true)
      expect(result.current.traffic.isSuccess).toBe(true)
    })

    expect(
      fetchMock.mock.calls.map(([request]) => new URL((request as Request).url).pathname).sort(),
    ).toEqual(['/api/me/devices', '/api/me/subscription', '/api/me/traffic', '/api/plans'])
    expect(queries.getQueryData(['plans'])).toEqual(PLANS)
    expect(queries.getQueryData(['subscription'])).toEqual(ACTIVE)
    expect(queries.getQueryData(['devices'])).toEqual(DEVICES)
    expect(queries.getQueryData(['traffic'])).toEqual(TRAFFIC)
  })

  it.each([
    ['pending', PENDING, 2],
    ['active', ACTIVE, 1],
  ] as const)(
    'опрашивает подписку %s только пока выдаётся доступ',
    async (_status, response, calls) => {
      const requestedAt: number[] = []
      const fetchMock = vi.fn(async (_request: Request) => {
        requestedAt.push(performance.now())
        return Response.json(response)
      })
      vi.stubGlobal('fetch', fetchMock)
      const { Wrapper } = createWrapper()
      const { result } = renderHook(useSubscription, { wrapper: Wrapper })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      if (calls === 2) {
        await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2), { timeout: 3500 })
        const firstRequestAt = requestedAt[0]
        const secondRequestAt = requestedAt[1]
        if (firstRequestAt === undefined || secondRequestAt === undefined)
          throw new Error('нет повторного запроса pending-подписки')
        const interval = secondRequestAt - firstRequestAt
        expect(interval).toBeGreaterThanOrEqual(2800)
        expect(interval).toBeLessThan(3500)
      } else {
        await new Promise<void>((resolve) => setTimeout(resolve, 3100))
      }

      expect(fetchMock).toHaveBeenCalledTimes(calls)
    },
  )

  it('заменяет кэш подписки ответом после активации триала', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json(PENDING, { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const { queries, Wrapper } = createWrapper()
    const { result } = renderHook(() => useActivateTrial('ru'), { wrapper: Wrapper })

    await result.current.mutateAsync()

    const request = fetchMock.mock.calls[0]?.[0]
    expect(request).toBeInstanceOf(Request)
    if (!request) throw new Error('не отправлен запрос активации триала')
    expect(request.url).toBe('https://api.test/api/me/subscription/trial')
    expect(request.method).toBe('POST')
    expect(queries.getQueryData(['subscription'])).toEqual(PENDING)
  })

  it('отправляет hwid и инвалидирует кэш устройств после отвязки', async () => {
    const fetchMock = vi.fn(async (_request: Request) => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const { queries, Wrapper } = createWrapper()
    queries.setQueryData(['devices'], DEVICES)
    const { result } = renderHook(() => useUnlinkDevice('ru'), { wrapper: Wrapper })

    await result.current.mutateAsync('hwid-1')

    const request = fetchMock.mock.calls[0]?.[0]
    expect(request).toBeInstanceOf(Request)
    if (!request) throw new Error('не отправлен запрос отвязки устройства')
    expect(request.url).toBe('https://api.test/api/me/devices/unlink')
    expect(request.method).toBe('POST')
    await expect(request.json()).resolves.toEqual({ hwid: 'hwid-1' })
    expect(queries.getQueryState(['devices'])?.isInvalidated).toBe(true)
  })
})
