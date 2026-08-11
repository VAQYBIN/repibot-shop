import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PROFILE, renderWithProviders, stubFetch } from '../test-utils'
import { Support } from './support'

const TICKET = {
  id: 41,
  status: 'waiting_user',
  subject: 'не открывается',
  created_at: '2026-08-11T12:00:00Z',
  last_staff_message_at: '2026-08-11T12:05:00Z',
}

const THREAD = {
  ticket: TICKET,
  messages: [
    { id: 1, author: 'user', body: 'не открывается', created_at: '2026-08-11T12:00:00Z' },
    { id: 2, author: 'staff', body: 'проверьте профиль', created_at: '2026-08-11T12:05:00Z' },
  ],
}

/** Ответы, общие для всех тестов экрана. `null` — путь не разобран. */
function supportHandlers(tickets: unknown[], thread: unknown = THREAD) {
  return (request: Request): Response | null => {
    const path = new URL(request.url).pathname
    if (path === '/api/me') return Response.json(PROFILE)
    if (path === '/api/support/tickets' && request.method === 'GET') return Response.json(tickets)
    if (path === '/api/support/tickets/41' && request.method === 'GET') return Response.json(thread)
    return null
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('поддержка в Mini App', () => {
  it('зовёт написать, когда обращений ещё нет', async () => {
    const base = supportHandlers([])
    stubFetch((request) => base(request) ?? new Response(null, { status: 404 }))

    renderWithProviders(<Support />)

    expect(await screen.findByText('Обращений пока нет')).toBeVisible()
    expect(screen.getByRole('form', { name: 'Новое обращение' })).toBeVisible()
  })

  it('отправляет новое обращение текстом человека', async () => {
    const base = supportHandlers([])
    const requests: Request[] = []
    stubFetch((request) => {
      const handled = base(request)
      if (handled !== null) return handled
      requests.push(request)
      return Response.json({ ...TICKET, status: 'waiting_staff' }, { status: 201 })
    })

    renderWithProviders(<Support />)

    const form = await screen.findByRole('form', { name: 'Новое обращение' })
    await userEvent.type(within(form).getByLabelText('Что произошло?'), 'не открывается')
    await userEvent.click(within(form).getByRole('button', { name: 'Отправить' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(new URL(requests[0]?.url ?? '').pathname).toBe('/api/support/tickets')
    expect(requests[0]?.method).toBe('POST')
    await expect(requests[0]?.json()).resolves.toEqual({ body: 'не открывается' })
  })

  it('показывает ответ поддержки в выбранной переписке', async () => {
    const base = supportHandlers([TICKET])
    stubFetch((request) => base(request) ?? new Response(null, { status: 404 }))

    renderWithProviders(<Support />)

    await userEvent.click(await screen.findByRole('button', { name: /не открывается/ }))

    const thread = await screen.findByRole('list', { name: 'не открывается' })
    expect(within(thread).getByText('проверьте профиль')).toBeVisible()
    expect(within(thread).getByText('Поддержка')).toBeVisible()
  })

  it('объясняет выключенную поддержку и убирает форму, в которую некому писать', async () => {
    const base = supportHandlers([])
    stubFetch(
      (request) =>
        base(request) ??
        Response.json({ error: { code: 'support_unavailable', message: 'нет' } }, { status: 409 }),
    )

    renderWithProviders(<Support />)

    const form = await screen.findByRole('form', { name: 'Новое обращение' })
    await userEvent.type(within(form).getByLabelText('Что произошло?'), 'привет')
    await userEvent.click(within(form).getByRole('button', { name: 'Отправить' }))

    expect(await screen.findByText('Поддержка сейчас недоступна')).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Новое обращение' })).not.toBeInTheDocument()
  })

  it('не даёт дописывать в закрытое обращение', async () => {
    const closed = { ...TICKET, status: 'closed' }
    const base = supportHandlers([closed], { ...THREAD, ticket: closed })
    stubFetch((request) => base(request) ?? new Response(null, { status: 404 }))

    renderWithProviders(<Support />)

    await userEvent.click(await screen.findByRole('button', { name: /не открывается/ }))

    expect(await screen.findByText('проверьте профиль')).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Ваш ответ' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Закрыть обращение' })).not.toBeInTheDocument()
  })

  it('спрашивает подтверждение, прежде чем закрыть обращение', async () => {
    const base = supportHandlers([TICKET])
    const requests: Request[] = []
    stubFetch((request) => {
      const handled = base(request)
      if (handled !== null) return handled
      requests.push(request)
      return Response.json({ ...TICKET, status: 'closed' })
    })

    renderWithProviders(<Support />)

    await userEvent.click(await screen.findByRole('button', { name: /не открывается/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Закрыть обращение' }))

    const dialog = screen.getByRole('dialog', { name: 'Закрыть обращение?' })
    expect(dialog).toBeVisible()
    expect(requests).toHaveLength(0)

    await userEvent.click(within(dialog).getByRole('button', { name: 'Закрыть обращение' }))

    await waitFor(() => expect(requests).toHaveLength(1))
    expect(new URL(requests[0]?.url ?? '').pathname).toBe('/api/support/tickets/41/close')
  })
})
