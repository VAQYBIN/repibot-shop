import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminBroadcastsPage from './page'

afterEach(() => vi.unstubAllGlobals())

function profile(role: string) {
  return {
    id: 1,
    email: 'admin@example.org',
    email_verified: true,
    telegram_username: null,
    name: null,
    language: 'ru',
    role,
    referral_code: 'ABC12345',
    has_password: true,
    has_telegram: false,
    passkey_count: 0,
  }
}

const DRAFT = {
  id: 7,
  segment: 'active',
  title: { ru: 'Плановые работы' },
  body: { ru: 'Ночью возможны перебои.' },
  status: 'draft',
  planned_count: 0,
  sent_count: 0,
  failed_count: 0,
  started_at: null,
  finished_at: null,
}

const RUNNING = {
  id: 8,
  segment: 'all',
  title: { ru: 'Летняя скидка' },
  body: { ru: 'Скидка 30% до конца недели.' },
  status: 'running',
  planned_count: 120,
  sent_count: 45,
  failed_count: 3,
  started_at: '2026-08-11T09:00:00Z',
  finished_at: null,
}

const DONE = {
  id: 9,
  segment: 'never_paid',
  title: { ru: 'Пробный период' },
  body: { ru: 'Попробуйте бесплатно.' },
  status: 'done',
  planned_count: 10,
  sent_count: 10,
  failed_count: 0,
  started_at: '2026-08-10T09:00:00Z',
  finished_at: '2026-08-10T09:05:00Z',
}

describe('админский экран рассылок', () => {
  it('показывает кампании со статусом и счётчиками', async () => {
    renderWithProviders(<AdminBroadcastsPage />, {
      handlers: {
        '/api/me': profile('admin'),
        '/api/admin/broadcasts': [RUNNING, DONE],
      },
    })

    const running = await screen.findByRole('row', { name: /Летняя скидка/ })
    expect(running).toHaveTextContent('Идёт')
    expect(running).toHaveTextContent('120')
    expect(running).toHaveTextContent('45')
    expect(running).toHaveTextContent('3')

    const done = screen.getByRole('row', { name: /Пробный период/ })
    expect(done).toHaveTextContent('Завершена')
  })

  it('запрашивает охват выбранного сегмента до создания кампании', async () => {
    const reach: Request[] = []
    renderWithProviders(<AdminBroadcastsPage />, {
      handlers: {
        '/api/me': profile('admin'),
        '/api/admin/broadcasts': [],
        '/api/admin/segments/never_paid/count': (request: Request) => {
          reach.push(request)
          return { count: 42 }
        },
      },
    })

    await userEvent.selectOptions(await screen.findByLabelText('Сегмент'), 'never_paid')

    expect(await screen.findByText('Охват сегмента: 42')).toBeInTheDocument()
    expect(reach).toHaveLength(1)
    expect(reach[0]?.method).toBe('GET')
  })

  it('создаёт черновик с обязательным русским текстом и необязательным английским', async () => {
    const created: Request[] = []
    renderWithProviders(<AdminBroadcastsPage />, {
      handlers: {
        '/api/me': profile('admin'),
        '/api/admin/broadcasts': (request: Request) => {
          if (request.method === 'GET') return []
          created.push(request)
          return { status: 201, body: DRAFT }
        },
        '/api/admin/segments/active/count': { count: 12 },
      },
    })

    const submit = await screen.findByRole('button', { name: 'Создать черновик' })
    expect(submit).toBeDisabled()

    await userEvent.selectOptions(screen.getByLabelText('Сегмент'), 'active')
    await userEvent.type(screen.getByLabelText('Заголовок по-русски'), 'Плановые работы')
    await userEvent.type(screen.getByLabelText('Текст по-русски'), 'Ночью возможны перебои.')
    await userEvent.click(submit)

    expect(created).toHaveLength(1)
    await expect(created[0]?.json()).resolves.toEqual({
      segment: 'active',
      title: { ru: 'Плановые работы' },
      body: { ru: 'Ночью возможны перебои.' },
    })
  })

  it('запускает кампанию только после подтверждения с числом получателей', async () => {
    const starts: Request[] = []
    renderWithProviders(<AdminBroadcastsPage />, {
      handlers: {
        '/api/me': profile('admin'),
        '/api/admin/broadcasts': [DRAFT],
        '/api/admin/segments/active/count': { count: 12 },
        '/api/admin/broadcasts/7/start': (request: Request) => {
          starts.push(request)
          return { ...DRAFT, status: 'running', planned_count: 12 }
        },
      },
    })

    const draft = await screen.findByRole('row', { name: /Плановые работы/ })
    await userEvent.click(within(draft).getByRole('button', { name: 'Запустить' }))

    const dialog = await screen.findByRole('dialog', { name: 'Запустить рассылку?' })
    expect(starts).toHaveLength(0)
    // Охват в подтверждении приходит отдельным запросом, поэтому его ждём.
    await waitFor(() => expect(dialog).toHaveTextContent('12 получателям'))

    await userEvent.click(within(dialog).getByRole('button', { name: 'Запустить рассылку' }))

    expect(starts).toHaveLength(1)
    expect(starts[0]?.method).toBe('POST')
  })

  it('даёт отменить идущую кампанию и ничего не предлагает завершённой', async () => {
    const cancels: Request[] = []
    renderWithProviders(<AdminBroadcastsPage />, {
      handlers: {
        '/api/me': profile('admin'),
        '/api/admin/broadcasts': [RUNNING, DONE],
        '/api/admin/broadcasts/8/cancel': (request: Request) => {
          cancels.push(request)
          return { ...RUNNING, status: 'canceled' }
        },
      },
    })

    const running = await screen.findByRole('row', { name: /Летняя скидка/ })
    expect(within(running).queryByRole('button', { name: 'Запустить' })).not.toBeInTheDocument()
    await userEvent.click(within(running).getByRole('button', { name: 'Отменить' }))
    expect(cancels).toHaveLength(1)

    const done = screen.getByRole('row', { name: /Пробный период/ })
    expect(within(done).queryByRole('button')).not.toBeInTheDocument()
  })

  it('отказывает роли поддержки вместо показа формы', async () => {
    renderWithProviders(<AdminBroadcastsPage />, {
      handlers: { '/api/me': profile('support') },
    })

    expect(await screen.findByText(/только администратору/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Сегмент')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
