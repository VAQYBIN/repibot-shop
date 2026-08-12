import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminUsersPage from './page'

afterEach(() => vi.unstubAllGlobals())

interface Row {
  id: number
  name: string | null
  email: string | null
  telegram_id: number | null
  telegram_username: string | null
  plan_name: string | null
  subscription_status: string | null
  expires_at: string | null
  banned: boolean
  support_muted: boolean
}

function makeRow(id: number, over: Partial<Row> = {}): Row {
  return {
    id,
    name: `Человек ${id}`,
    email: `user${id}@example.com`,
    telegram_id: 700_000 + id,
    telegram_username: `user${id}`,
    plan_name: 'Год',
    subscription_status: 'active',
    expires_at: '2026-12-01T00:00:00.000Z',
    banned: false,
    support_muted: false,
    ...over,
  }
}

function table() {
  return screen.findByRole('table', { name: 'Пользователи' })
}

function searchParam(request: Request | undefined, name: string): string | null {
  return request === undefined ? null : new URL(request.url).searchParams.get(name)
}

describe('админский список пользователей', () => {
  it('ищет по одной строке любым опознавателем', async () => {
    // Сотрудник не знает, что ему дали — почту, ссылку на Telegram или номер:
    // разбираться должен сервер, а не человек, поэтому строка уходит как есть.
    const requests: Request[] = []
    renderWithProviders(<AdminUsersPage />, {
      handlers: {
        '/api/admin/users': (request: Request) => {
          requests.push(request)
          return [makeRow(1, { name: 'Вася', telegram_username: 'vasya' })]
        },
      },
    })

    await table()
    await userEvent.type(screen.getByLabelText('Поиск'), '@vasya')

    // Второй запрос — один на всю набранную строку: без задержки ввода их было
    // бы шесть, по одному на букву.
    await waitFor(() =>
      expect(requests.map((request) => searchParam(request, 'query'))).toEqual(['', '@vasya']),
    )
    expect(within(await table()).getByRole('link', { name: 'Вася' })).toHaveAttribute(
      'href',
      '/admin/users/1',
    )
  })

  it('показывает ограничения человека прямо в строке', async () => {
    renderWithProviders(<AdminUsersPage />, {
      handlers: {
        '/api/admin/users': [makeRow(1, { banned: true, support_muted: true })],
      },
    })

    const inside = within(await table())
    expect(inside.getByLabelText('Заблокирован')).toBeInTheDocument()
    expect(inside.getByLabelText('Поддержка закрыта')).toBeInTheDocument()
  })

  it('вместо пустой таблицы говорит, что никого не нашли', async () => {
    renderWithProviders(<AdminUsersPage />, { handlers: { '/api/admin/users': [] } })

    expect(await screen.findByText('Никого не нашли')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Показать ещё' })).not.toBeInTheDocument()
  })

  it('дописывает строки кнопкой «ещё», а не заменяет их', async () => {
    const requests: Request[] = []
    const first = Array.from({ length: 20 }, (_, index) => makeRow(index + 1))
    renderWithProviders(<AdminUsersPage />, {
      handlers: {
        '/api/admin/users': (request: Request) => {
          requests.push(request)
          return searchParam(request, 'offset') === '0' ? first : [makeRow(21)]
        },
      },
    })

    expect(within(await table()).getAllByRole('row')).toHaveLength(21)

    await userEvent.click(screen.getByRole('button', { name: 'Показать ещё' }))

    await waitFor(async () => expect(within(await table()).getAllByRole('row')).toHaveLength(22))
    const inside = within(await table())
    // Первая страница осталась на месте: «ещё» дописывает, а не перелистывает.
    expect(inside.getByRole('link', { name: 'Человек 1' })).toBeInTheDocument()
    expect(inside.getByRole('link', { name: 'Человек 21' })).toBeInTheDocument()
    expect(searchParam(requests[1], 'offset')).toBe('20')
    // Страница неполная — просить дальше нечего.
    expect(screen.queryByRole('button', { name: 'Показать ещё' })).not.toBeInTheDocument()
  })
})
