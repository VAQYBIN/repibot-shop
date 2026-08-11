import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/hooks'
import { createTokenStore } from '../auth/store'
import {
  useAutoRenew,
  useCreateOrder,
  useOrders,
  usePaymentMethod,
  useRedeemGift,
  useStartCardBinding,
  useUnlinkCard,
} from './hooks'

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

const CARD = {
  title: 'Visa •••• 4242',
  linked_at: '2026-08-01T12:00:00Z',
  binding_available: true,
} as const

/** staleTime задаётся тестом: в приложении снимок живёт 30 секунд. */
function createWrapper(staleTime = 0) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime } } })
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

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  // Признак активности глобальный: без сброса он утёк бы в следующий тест.
  focusManager.setFocused(undefined)
})

describe('hooks заказов и оплаты', () => {
  it('грузит историю заказов только текущего пользователя', async () => {
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

  it('создаёт заказ YooKassa, заменяет его в кэше и сбрасывает зависимые данные', async () => {
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
        return_surface: 'web',
      })
    })

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/me/orders')
    expect(request.method).toBe('POST')
    // Поверхность возврата уходит как есть: адрес по ней строит сервер, а хук
    // ничего к телу заказа не добавляет и ничего из него не выбрасывает.
    await expect(request.json()).resolves.toEqual({
      plan_id: 2,
      purpose: 'purchase',
      provider: 'yookassa',
      promo_code: 'WELCOME',
      idempotency_key: 'order-41',
      return_surface: 'web',
    })
    expect(queryClient.getQueryData(['orders'])).toEqual([ORDER])
    expect(queryClient.getQueryState(['orders'])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(['subscription'])?.isInvalidated).toBe(true)
  })

  it('переводит устойчивый код ошибки оплаты на выбранный язык', async () => {
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
        return_surface: 'miniapp',
      }),
    ).rejects.toThrow('Payment provider is unavailable')
  })

  it('погашает подарок и обновляет подписку вместе с историей ваучеров', async () => {
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

  it('откатывает оптимистичное переключение автопродления при отказе сервера', async () => {
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

  it('оставляет значение автопродления, подтверждённое эндпоинтом', async () => {
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

  it('берёт сохранённую карту у сервера и держит её под отдельным ключом кэша', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json(CARD))
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(usePaymentMethod, { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/me/payment-method')
    expect(request.method).toBe('GET')
    expect(queryClient.getQueryData(['payment-method'])).toEqual(CARD)
  })

  it('отвязывает карту и сбрасывает вместе с ней снимок подписки', async () => {
    const fetchMock = vi.fn(async (_request: Request) => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    queryClient.setQueryData(['payment-method'], CARD)
    queryClient.setQueryData(['subscription'], SUBSCRIPTION)
    const { result } = renderHook(() => useUnlinkCard('ru'), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync()
    })

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/me/payment-method')
    expect(request.method).toBe('DELETE')
    // Автоплатёж выключает сервер, поэтому подписку тоже перечитываем.
    expect(queryClient.getQueryState(['payment-method'])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(['subscription'])?.isInvalidated).toBe(true)
  })

  it('начинает привязку карты и возвращает адрес формы провайдера', async () => {
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json({ confirmation_url: 'https://yookassa.test/bind/7' }, { status: 201 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useStartCardBinding('ru'), { wrapper: Wrapper })

    await expect(result.current.mutateAsync({ return_surface: 'web' })).resolves.toEqual({
      confirmation_url: 'https://yookassa.test/bind/7',
    })

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/me/payment-method/bindings')
    expect(request.method).toBe('POST')
    // Тело обязательно: по нему сервер решает, куда провайдер вернёт плательщика.
    await expect(request.json()).resolves.toEqual({ return_surface: 'web' })
  })

  it('шлёт привязке ту поверхность, с которой её начали', async () => {
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json({ confirmation_url: 'https://yookassa.test/bind/8' }, { status: 201 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useStartCardBinding('ru'), { wrapper: Wrapper })

    await result.current.mutateAsync({ return_surface: 'miniapp' })

    // Из Mini App возвращать на сайт нельзя: вне Telegram тот экран не работает.
    const request = fetchMock.mock.calls[0]?.[0] as Request
    await expect(request.json()).resolves.toEqual({ return_surface: 'miniapp' })
  })

  it('спрашивает о заказе, пока его исход неизвестен, и прекращает после выдачи', async () => {
    /* Оплату подтверждает вебхук провайдера, а доступ выдаёт очередь: обе
       новости приходят на сервер, а не в открытую страницу. */
    const answers = [
      [{ ...ORDER, status: 'pending', expires_at: '2100-01-01T00:00:00Z' }],
      [{ ...ORDER, status: 'fulfilled', expires_at: '2100-01-01T00:00:00Z' }],
    ]
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json(answers[Math.min(fetchMock.mock.calls.length - 1, 1)]),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.useFakeTimers()
    const { Wrapper } = createWrapper(30_000)
    const { result } = renderHook(useOrders, { wrapper: Wrapper })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(result.current.data?.[0]?.status).toBe('pending')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4100)
    })
    expect(result.current.data?.[0]?.status).toBe('fulfilled')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('не спрашивает о заказе, срок оплаты которого уже прошёл', async () => {
    /* Брошенный заказ остаётся pending до сверки; спрашивать о нём каждые
       несколько секунд значит ждать новости, которой не будет. */
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json([{ ...ORDER, status: 'pending', expires_at: '2020-01-01T00:00:00Z' }]),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.useFakeTimers()
    const { Wrapper } = createWrapper(30_000)
    renderHook(useOrders, { wrapper: Wrapper })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('спрашивает о карте, пока провайдер не ответил по начатой привязке', async () => {
    /* Ответ провайдера приходит не в тот момент, когда человек вернулся в
       приложение: между возвращением и ответом проходят секунды, и один
       запрос на возврате попадает ровно в этот промежуток. */
    const answers = [
      { ...CARD, title: null, linked_at: null, binding_pending: true },
      { ...CARD, binding_pending: false },
    ]
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json(answers[Math.min(fetchMock.mock.calls.length - 1, 1)]),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.useFakeTimers()
    const { queryClient, Wrapper } = createWrapper(30_000)
    queryClient.setQueryData(['subscription'], SUBSCRIPTION)
    const { result } = renderHook(usePaymentMethod, { wrapper: Wrapper })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.data?.binding_pending).toBe(true)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    // Ответ приходит не мгновенно, как и от настоящей сети.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(result.current.data?.title).toBe('Visa •••• 4242')
    // Привязка включает автоплатёж на сервере: снимок подписки после неё устарел.
    expect(queryClient.getQueryState(['subscription'])?.isInvalidated).toBe(true)

    // Ждать больше нечего — вопросы прекращаются.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('перечитывает карту и заказы, когда человек возвращается в приложение', async () => {
    /* Пока человек на форме провайдера, карта и заказ меняются без нашего
       участия, а снимок в кэше остаётся свежим: возврат должен перечитать их
       независимо от срока годности снимка, иначе экран покажет прошлое. */
    const fetchMock = vi.fn(async (request: Request) =>
      new URL(request.url).pathname === '/api/me/payment-method'
        ? Response.json(CARD)
        : Response.json([ORDER]),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { Wrapper } = createWrapper(30_000)
    const { result } = renderHook(() => ({ card: usePaymentMethod(), orders: useOrders() }), {
      wrapper: Wrapper,
    })
    await waitFor(() => {
      expect(result.current.card.isSuccess).toBe(true)
      expect(result.current.orders.isSuccess).toBe(true)
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)

    act(() => focusManager.setFocused(false))
    act(() => focusManager.setFocused(true))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))
  })

  it('переводит отказ провайдера привязать карту без оплаты', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'binding_unavailable' } }, { status: 409 })),
    )
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useStartCardBinding('ru'), { wrapper: Wrapper })

    await expect(result.current.mutateAsync({ return_surface: 'web' })).rejects.toThrow(
      'Привязка карты без оплаты сейчас недоступна',
    )
  })
})
