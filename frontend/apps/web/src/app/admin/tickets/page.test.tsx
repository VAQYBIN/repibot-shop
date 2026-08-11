import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminTicketsPage from './page'

afterEach(() => vi.unstubAllGlobals())

const tickets = [
  {
    id: 7,
    status: 'waiting_staff',
    subject: 'Не приходит подписка',
    created_at: '2026-08-10T09:00:00.000Z',
    last_staff_message_at: null,
    user_id: 42,
    telegram_topic_id: null,
  },
  {
    id: 8,
    status: 'closed',
    subject: 'Вопрос по оплате',
    created_at: '2026-08-09T09:00:00.000Z',
    last_staff_message_at: '2026-08-09T10:00:00.000Z',
    user_id: 43,
    telegram_topic_id: 12,
  },
]

const firstMessage = {
  id: 1,
  author: 'user',
  body: 'Оплатил, но доступа нет.',
  created_at: '2026-08-10T09:00:00.000Z',
}

describe('админский экран обращений', () => {
  it('показывает обращения списком', async () => {
    renderWithProviders(<AdminTicketsPage />, {
      handlers: { '/api/admin/tickets': tickets },
    })

    const list = await screen.findByRole('list', { name: 'Обращения' })
    expect(within(list).getByRole('button', { name: /Не приходит подписка/ })).toBeInTheDocument()
    expect(within(list).getByRole('button', { name: /Вопрос по оплате/ })).toBeInTheDocument()
  })

  it('передаёт выбранный статус в запрос списка', async () => {
    const requests: Request[] = []
    renderWithProviders(<AdminTicketsPage />, {
      handlers: {
        '/api/admin/tickets': (request: Request) => {
          requests.push(request)
          return tickets
        },
      },
    })

    await screen.findByRole('list', { name: 'Обращения' })
    await userEvent.selectOptions(screen.getByLabelText('Статус'), 'waiting_staff')

    await expect
      .poll(() => requests.map((request) => new URL(request.url).searchParams.get('status')))
      .toEqual([null, 'waiting_staff'])
  })

  it('отправляет ответ сотрудника и показывает его в переписке', async () => {
    const requests: Request[] = []
    const messages = [firstMessage]
    renderWithProviders(<AdminTicketsPage />, {
      handlers: {
        '/api/admin/tickets': tickets,
        '/api/admin/tickets/7': () => ({
          status: 200,
          body: {
            ticket: {
              id: 7,
              status: 'waiting_staff',
              subject: 'Не приходит подписка',
              created_at: '2026-08-10T09:00:00.000Z',
              last_staff_message_at: null,
            },
            messages,
          },
        }),
        '/api/admin/tickets/7/messages': async (request: Request) => {
          requests.push(request)
          const body = (await request.clone().json()) as { body: string }
          const created = {
            id: 2,
            author: 'staff',
            body: body.body,
            created_at: '2026-08-10T10:00:00.000Z',
          }
          messages.push(created)
          return { status: 201, body: created }
        },
      },
    })

    const list = await screen.findByRole('list', { name: 'Обращения' })
    await userEvent.click(within(list).getByRole('button', { name: /Не приходит подписка/ }))

    expect(await screen.findByText('Оплатил, но доступа нет.')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Ответ поддержки'), 'Проверили, доступ выдан.')
    await userEvent.click(screen.getByRole('button', { name: 'Отправить ответ' }))

    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    await expect(requests[0]?.json()).resolves.toEqual({ body: 'Проверили, доступ выдан.' })
    expect(await screen.findByText('Проверили, доступ выдан.')).toBeInTheDocument()
  })
})
