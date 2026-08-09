import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/hooks'
import { createTokenStore } from '../auth/store'
import { useAutoRenew, useCreateOrder, useOrders, useRedeemGift } from './hooks'

const ORDER = {
  id: 41,
  purpose: 'purchase',
  plan_id: 2,
  plan_code: 'month',
  plan_name: { ru: 'Месяц', en: 'Month' },
  duration_days: 30,
  price_rub: '299.00',
  price_stars: 199,
  gross_rub: '299.00',
  discount_rub: '0.00',
  amount_due_rub: '254.15',
  status: 'pending',
  expires_at: '2026-09-05T12:00:00Z',
  confirmation_url: 'https://pay.example.test/41',
  telegram_invoice_required: false,
  telegram_handoff_url: null,
} as const

const SUBSCRIPTION = {
  subscription: {
    plan_code: 'month',
    plan_name: { ru: 'Месяц', en: 'Month' },
    status: 'active',
    started_at: '2026-08-06T12:00:00Z',
    expires_at: '2026-09-05T12:00:00Z',
    subscription_url: 'https://panel.example.test/sub/abc',
    traffic_limit_bytes: 0,
    hwid_device_limit: 3,
    auto_renew_enabled: false,
  },
  trial_available: false,
} as const

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider baseUrl="https://api.test" store={createTokenStore()}>
          {children}
        </AuthProvider>
      </QueryClientProvider>
    )
  }
  return { queryClient, Wrapper }
}

afterEach(() => vi.unstubAllGlobals())

describe('hooks заказов и оплаты', () => {
  it('loads only the authenticated user order history under the orders key', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json([ORDER]))
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(useOrders, { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/me/orders')
    expect(request.method).toBe('GET')
    expect(queryClient.getQueryData(['orders'])).toEqual([ORDER])
  })

  it('creates a YooKassa order, replaces its order cache and invalidates dependent data', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json(ORDER, { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    queryClient.setQueryData(['orders'], [])
    queryClient.setQueryData(['subscription'], SUBSCRIPTION)
    const { result } = renderHook(() => useCreateOrder('ru'), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        plan_id: 2,
        purpose: 'purchase',
        provider: 'yookassa',
        promo_code: 'WELCOME',
        idempotency_key: 'order-41',
        save_payment_method: true,
      })
    })

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/me/orders')
    expect(request.method).toBe('POST')
    await expect(request.json()).resolves.toEqual({
      plan_id: 2,
      purpose: 'purchase',
      provider: 'yookassa',
      promo_code: 'WELCOME',
      idempotency_key: 'order-41',
      save_payment_method: true,
    })
    expect(queryClient.getQueryData(['orders'])).toEqual([ORDER])
    expect(queryClient.getQueryState(['orders'])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(['subscription'])?.isInvalidated).toBe(true)
  })

  it('maps a stable payment API error into the chosen language', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ error: { code: 'provider_unavailable' } }, { status: 503 }),
      ),
    )
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useCreateOrder('en'), { wrapper: Wrapper })

    await expect(
      result.current.mutateAsync({
        plan_id: 2,
        purpose: 'renew',
        provider: 'yookassa',
        idempotency_key: 'renew-41',
        save_payment_method: false,
      }),
    ).rejects.toThrow('Payment provider is unavailable')
  })

  it('redeems a gift and refreshes both the subscription and voucher history', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json(SUBSCRIPTION))
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    queryClient.setQueryData(['subscription'], { subscription: null, trial_available: true })
    queryClient.setQueryData(['gifts'], [{ code: 'GIFT-41' }])
    const { result } = renderHook(() => useRedeemGift('ru'), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({ code: 'GIFT-41' })
    })

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/me/gifts/redeem')
    expect(request.method).toBe('POST')
    await expect(request.json()).resolves.toEqual({ code: 'GIFT-41' })
    expect(queryClient.getQueryData(['subscription'])).toEqual(SUBSCRIPTION)
    expect(queryClient.getQueryState(['gifts'])?.isInvalidated).toBe(true)
  })

  it('rolls back the optimistic auto-renew switch when the server rejects it', async () => {
    let rejectRequest: ((value: Response) => void) | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            rejectRequest = resolve
          }),
      ),
    )
    const { queryClient, Wrapper } = createWrapper()
    queryClient.setQueryData(['subscription'], SUBSCRIPTION)
    const { result } = renderHook(() => useAutoRenew('ru'), { wrapper: Wrapper })

    const mutation = result.current.mutateAsync({ auto_renew_enabled: true })
    await waitFor(() => {
      expect(
        queryClient.getQueryData<typeof SUBSCRIPTION>(['subscription'])?.subscription
          ?.auto_renew_enabled,
      ).toBe(true)
    })
    const request = vi.mocked(fetch).mock.calls[0]?.[0]
    if (!(request instanceof Request)) throw new Error('не отправлен запрос автопродления')
    expect(request.url).toBe('https://api.test/api/me/subscription/auto-renew')
    expect(request.method).toBe('PUT')
    await expect(request.json()).resolves.toEqual({ auto_renew_enabled: true })
    rejectRequest?.(Response.json({ error: { code: 'auto_renew_unavailable' } }, { status: 409 }))

    await expect(mutation).rejects.toThrow('Автопродление сейчас недоступно')
    expect(queryClient.getQueryData(['subscription'])).toEqual(SUBSCRIPTION)
  })

  it('keeps the auto-renew value confirmed by the typed endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_request: Request) => Response.json({ auto_renew_enabled: false })),
    )
    const { queryClient, Wrapper } = createWrapper()
    queryClient.setQueryData(['subscription'], SUBSCRIPTION)
    const { result } = renderHook(() => useAutoRenew('en'), { wrapper: Wrapper })

    await result.current.mutateAsync({ auto_renew_enabled: true })

    expect(queryClient.getQueryData(['subscription'])).toEqual(SUBSCRIPTION)
  })
})
