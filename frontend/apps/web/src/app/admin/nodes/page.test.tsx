import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminNodesPage from './page'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

interface Node {
  name: string
  country_code: string
  address: string
  port: number | null
  is_connected: boolean
  is_disabled: boolean
  users_online: number
  traffic_used_bytes: number
  traffic_limit_bytes: number
  xray_uptime_seconds: number
  last_status_message: string | null
}

function node(overrides: Partial<Node> = {}): Node {
  return {
    name: 'Амстердам',
    country_code: 'NL',
    address: '10.0.0.1',
    port: 2222,
    is_connected: true,
    is_disabled: false,
    users_online: 12,
    traffic_used_bytes: 1_610_612_736,
    traffic_limit_bytes: 10_737_418_240,
    xray_uptime_seconds: 9000,
    last_status_message: null,
    ...overrides,
  }
}

const PANEL_UNAVAILABLE = {
  status: 503,
  body: { error: { code: 'panel_unavailable', message: 'panel is silent' } },
}

describe('админский экран нод', () => {
  it('различает выключенную ноду и потерявшую связь', async () => {
    // Выключил её человек, а связь пропала сама: путать эти два состояния
    // значит будить дежурного из-за плановых работ.
    renderWithProviders(<AdminNodesPage />, {
      handlers: {
        '/api/admin/nodes': [
          node({
            name: 'Амстердам',
            is_disabled: true,
            is_connected: false,
            last_status_message: 'Плановые работы до утра',
          }),
          node({ name: 'Франкфурт', is_disabled: false, is_connected: false }),
        ],
      },
    })

    const disabled = within(await screen.findByRole('article', { name: 'Амстердам' }))
    expect(disabled.getByText('Выключена')).toBeVisible()
    expect(disabled.queryByText('Нет связи')).toBeNull()
    // Последнее сообщение о состоянии читают ровно тогда, когда что-то не так.
    expect(disabled.getByText('Плановые работы до утра')).toBeVisible()

    const offline = within(screen.getByRole('article', { name: 'Франкфурт' }))
    expect(offline.getByText('Нет связи')).toBeVisible()
    expect(offline.queryByText('Выключена')).toBeNull()
  })

  it('на отказ панели предлагает повторить, а не показывает пустой список', async () => {
    let attempt = 0
    renderWithProviders(<AdminNodesPage />, {
      handlers: {
        '/api/admin/nodes': () => {
          attempt += 1
          return attempt === 1 ? PANEL_UNAVAILABLE : [node({ name: 'Амстердам' })]
        },
      },
    })

    expect(await screen.findByRole('alert')).toHaveTextContent(/панел/i)
    // Пустая таблица читалась бы как «узлов нет» — а узлы просто не спросили.
    expect(screen.queryByRole('article')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }))

    expect(await screen.findByRole('article', { name: 'Амстердам' })).toBeVisible()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('нулевой лимит трафика показывает как «без лимита»', async () => {
    renderWithProviders(<AdminNodesPage />, {
      handlers: {
        '/api/admin/nodes': [node({ traffic_used_bytes: 1_610_612_736, traffic_limit_bytes: 0 })],
      },
    })

    const card = within(await screen.findByRole('article', { name: 'Амстердам' }))
    expect(card.getByText(/1,5 ГБ/)).toBeVisible()
    expect(card.getByText(/без лимита/)).toBeVisible()
    // «0 Б» прочиталось бы как «лимит исчерпан», то есть ровно наоборот.
    expect(card.queryByText(/0 Б/)).toBeNull()
  })

  it('перечитывает список сам, пока страница открыта', async () => {
    // Состояние узла меняется само, а открывают эту страницу ровно тогда,
    // когда ждут изменений.
    vi.useFakeTimers()
    let calls = 0
    renderWithProviders(<AdminNodesPage />, {
      handlers: {
        '/api/admin/nodes': () => {
          calls += 1
          return [node()]
        },
      },
    })

    // Часы поддельные, поэтому ждать нечего: время двигаем руками, а act
    // впускает в React ответ, пришедший от такого прыжка.
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(calls).toBe(1)

    await act(() => vi.advanceTimersByTimeAsync(30_000))
    expect(calls).toBe(2)
  })
})
