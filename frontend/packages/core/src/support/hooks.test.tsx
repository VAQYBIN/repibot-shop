import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/hooks'
import { createTokenStore } from '../auth/store'
import {
  supportErrorCode,
  useCloseTicket,
  useOpenTicket,
  useReplyToTicket,
  useTicket,
  useTickets,
} from './hooks'

const TICKET = {
  id: 41,
  status: 'waiting_staff',
  subject: 'не открывается',
  created_at: '2026-08-11T12:00:00Z',
  last_staff_message_at: null,
} as const

const THREAD = {
  ticket: TICKET,
  messages: [{ id: 1, author: 'user', body: 'не открывается', created_at: '2026-08-11T12:00:00Z' }],
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
})

describe('hooks поддержки', () => {
  it('грузит список обращений человека', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json([TICKET]))
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    const { result } = renderHook(useTickets, { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/support/tickets')
    expect(request.method).toBe('GET')
    expect(queryClient.getQueryData(['tickets'])).toEqual([TICKET])
  })

  it('читает переписку выбранного обращения и молчит, пока обращение не выбрано', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json(THREAD))
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    const { result, rerender } = renderHook((id: number | null) => useTicket(id), {
      wrapper: Wrapper,
      initialProps: null as number | null,
    })

    expect(fetchMock).not.toHaveBeenCalled()
    rerender(41)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/support/tickets/41')
    expect(request.method).toBe('GET')
    expect(queryClient.getQueryData(['ticket', 41])).toEqual(THREAD)
  })

  it('открывает обращение и сбрасывает список, где сменился состав', async () => {
    const fetchMock = vi.fn(async (_request: Request) => Response.json(TICKET, { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    queryClient.setQueryData(['tickets'], [])
    const { result } = renderHook(() => useOpenTicket('ru'), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({ body: 'не открывается' })
    })

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/support/tickets')
    expect(request.method).toBe('POST')
    await expect(request.json()).resolves.toEqual({ body: 'не открывается' })
    expect(queryClient.getQueryState(['tickets'])?.isInvalidated).toBe(true)
  })

  it('после ответа перечитывает и переписку, и список: в списке сменился статус', async () => {
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json(
        { id: 2, author: 'user', body: 'ещё раз', created_at: '2026-08-11T13:00:00Z' },
        {
          status: 201,
        },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    queryClient.setQueryData(['tickets'], [TICKET])
    queryClient.setQueryData(['ticket', 41], THREAD)
    const { result } = renderHook(() => useReplyToTicket('ru'), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync({ ticketId: 41, body: 'ещё раз' })
    })

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/support/tickets/41/messages')
    expect(request.method).toBe('POST')
    await expect(request.json()).resolves.toEqual({ body: 'ещё раз' })
    expect(queryClient.getQueryState(['ticket', 41])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(['tickets'])?.isInvalidated).toBe(true)
  })

  it('закрывает обращение и перечитывает его вместе со списком', async () => {
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json({ ...TICKET, status: 'closed' }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { queryClient, Wrapper } = createWrapper()
    queryClient.setQueryData(['tickets'], [TICKET])
    queryClient.setQueryData(['ticket', 41], THREAD)
    const { result } = renderHook(() => useCloseTicket('ru'), { wrapper: Wrapper })

    await act(async () => {
      await result.current.mutateAsync(41)
    })

    const request = fetchMock.mock.calls[0]?.[0] as Request
    expect(request.url).toBe('https://api.test/api/support/tickets/41/close')
    expect(request.method).toBe('POST')
    expect(queryClient.getQueryState(['ticket', 41])?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(['tickets'])?.isInvalidated).toBe(true)
  })

  it('спрашивает о переписке, пока ход за поддержкой, и замолкает после ответа', async () => {
    /* Ответ приходит на сервер, а не в открытую страницу: человек ждёт его и
       не должен перезагружать экран, чтобы увидеть. */
    const answers = [
      THREAD,
      {
        ticket: {
          ...TICKET,
          status: 'waiting_user',
          last_staff_message_at: '2026-08-11T12:05:00Z',
        },
        messages: [
          ...THREAD.messages,
          { id: 2, author: 'staff', body: 'проверьте', created_at: '2026-08-11T12:05:00Z' },
        ],
      },
    ]
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json(answers[Math.min(fetchMock.mock.calls.length - 1, 1)]),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.useFakeTimers()
    const { Wrapper } = createWrapper(30_000)
    const { result } = renderHook(() => useTicket(41), { wrapper: Wrapper })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(result.current.data?.ticket.status).toBe('waiting_staff')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_100)
    })
    expect(result.current.data?.ticket.status).toBe('waiting_user')

    // Ход за человеком — спрашивать больше не о чем.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('не спрашивает о закрытом обращении', async () => {
    const fetchMock = vi.fn(async (_request: Request) =>
      Response.json({ ...THREAD, ticket: { ...TICKET, status: 'closed' } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    vi.useFakeTimers()
    const { Wrapper } = createWrapper(30_000)
    renderHook(() => useTicket(41), { wrapper: Wrapper })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('объясняет выключенную поддержку и сохраняет код отказа для экрана', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'support_unavailable' } }, { status: 409 })),
    )
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useOpenTicket('ru'), { wrapper: Wrapper })

    await expect(result.current.mutateAsync({ body: 'привет' })).rejects.toThrow(
      'Поддержка сейчас недоступна',
    )
    // Экран прячет форму по коду, а не по тексту: тексты переводятся.
    await waitFor(() => expect(supportErrorCode(result.current.error)).toBe('support_unavailable'))
  })

  it('переводит отказ переполненного списка обращений', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'too_many_tickets' } }, { status: 409 })),
    )
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useOpenTicket('en'), { wrapper: Wrapper })

    await expect(result.current.mutateAsync({ body: 'hi' })).rejects.toThrow(
      'Too many open requests — close one of them first',
    )
  })

  it('переводит отказ дописать в закрытое обращение', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'ticket_closed' } }, { status: 409 })),
    )
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useReplyToTicket('ru'), { wrapper: Wrapper })

    await expect(result.current.mutateAsync({ ticketId: 41, body: 'ещё' })).rejects.toThrow(
      'Обращение закрыто. Откройте новое',
    )
  })

  it('просит подождать, когда сообщения идут слишком часто', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'rate_limited' } }, { status: 429 })),
    )
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useReplyToTicket('ru'), { wrapper: Wrapper })

    // Пауза здесь своя: у поддержки она короче, чем у входа, и фраза другая.
    await expect(result.current.mutateAsync({ ticketId: 41, body: 'ещё' })).rejects.toThrow(
      'Слишком часто. Подождите несколько секунд',
    )
  })
})
