import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import SupportPage from './page'

const PROFILE = {
  id: 1,
  email: 'user@example.org',
  email_verified: true,
  telegram_username: null,
  name: null,
  language: 'ru',
  role: 'user',
  referral_code: 'ABC12345',
  has_password: true,
  has_telegram: false,
  passkey_count: 0,
}

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

function sentBody(method: string): Promise<unknown> | undefined {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
  const call = mock.mock.calls.find(([request]) => (request as Request).method === method)
  return (call?.[0] as Request | undefined)?.json()
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('поддержка в кабинете', () => {
  it('зовёт написать, когда обращений ещё нет', async () => {
    renderWithProviders(<SupportPage />, {
      handlers: { '/api/me': PROFILE, '/api/support/tickets': [] },
    })

    expect(await screen.findByText('Обращений пока нет')).toBeVisible()
    expect(screen.getByRole('form', { name: 'Новое обращение' })).toBeVisible()
  })

  it('отправляет новое обращение текстом человека', async () => {
    renderWithProviders(<SupportPage />, {
      handlers: {
        '/api/me': PROFILE,
        '/api/support/tickets': (request: Request) =>
          request.method === 'POST'
            ? { status: 201, body: { ...TICKET, status: 'waiting_staff' } }
            : [],
      },
    })

    const form = await screen.findByRole('form', { name: 'Новое обращение' })
    await userEvent.type(within(form).getByLabelText('Что произошло?'), 'не открывается')
    await userEvent.click(within(form).getByRole('button', { name: 'Отправить' }))

    await waitFor(async () => {
      await expect(sentBody('POST')).resolves.toEqual({ body: 'не открывается' })
    })
  })

  it('показывает ответ поддержки в выбранной переписке', async () => {
    renderWithProviders(<SupportPage />, {
      handlers: {
        '/api/me': PROFILE,
        '/api/support/tickets': [TICKET],
        '/api/support/tickets/41': THREAD,
      },
    })

    await userEvent.click(await screen.findByRole('button', { name: /не открывается/ }))

    const thread = await screen.findByRole('list', { name: 'не открывается' })
    expect(within(thread).getByText('проверьте профиль')).toBeVisible()
    expect(within(thread).getByText('Поддержка')).toBeVisible()
  })

  it('объясняет выключенную поддержку и убирает форму, в которую некому писать', async () => {
    renderWithProviders(<SupportPage />, {
      handlers: {
        '/api/me': PROFILE,
        '/api/support/tickets': (request: Request) =>
          request.method === 'POST'
            ? { status: 409, body: { error: { code: 'support_unavailable', message: 'нет' } } }
            : [],
      },
    })

    const form = await screen.findByRole('form', { name: 'Новое обращение' })
    await userEvent.type(within(form).getByLabelText('Что произошло?'), 'привет')
    await userEvent.click(within(form).getByRole('button', { name: 'Отправить' }))

    expect(await screen.findByText('Поддержка сейчас недоступна')).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Новое обращение' })).not.toBeInTheDocument()
  })

  it('не даёт дописывать в закрытое обращение', async () => {
    renderWithProviders(<SupportPage />, {
      handlers: {
        '/api/me': PROFILE,
        '/api/support/tickets': [{ ...TICKET, status: 'closed' }],
        '/api/support/tickets/41': {
          ...THREAD,
          ticket: { ...TICKET, status: 'closed' },
        },
      },
    })

    await userEvent.click(await screen.findByRole('button', { name: /не открывается/ }))

    expect(await screen.findByText('проверьте профиль')).toBeVisible()
    expect(screen.queryByRole('form', { name: 'Ваш ответ' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Закрыть обращение' })).not.toBeInTheDocument()
  })

  it('спрашивает подтверждение, прежде чем закрыть обращение', async () => {
    renderWithProviders(<SupportPage />, {
      handlers: {
        '/api/me': PROFILE,
        '/api/support/tickets': [TICKET],
        '/api/support/tickets/41': THREAD,
        '/api/support/tickets/41/close': { ...TICKET, status: 'closed' },
      },
    })

    await userEvent.click(await screen.findByRole('button', { name: /не открывается/ }))
    await userEvent.click(await screen.findByRole('button', { name: 'Закрыть обращение' }))

    const dialog = screen.getByRole('dialog', { name: 'Закрыть обращение?' })
    expect(dialog).toBeVisible()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Закрыть обращение' }))

    await waitFor(() => {
      const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
      const closed = mock.mock.calls.find(([request]) =>
        (request as Request).url.endsWith('/api/support/tickets/41/close'),
      )
      expect(closed).toBeDefined()
    })
  })
})
