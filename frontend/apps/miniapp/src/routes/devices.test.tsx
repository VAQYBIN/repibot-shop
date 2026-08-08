import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PROFILE, renderWithProviders, stubFetch, withRussianLocale } from '../test-utils'
import { Devices } from './devices'

const ONE_DEVICE = {
  devices: [
    {
      hwid: 'hwid-1',
      platform: 'iOS',
      device_model: 'iPhone 15',
      os_version: '18.0',
      created_at: '2026-08-06T12:00:00Z',
    },
  ],
  limit: 3,
  used: 1,
}

function devicesFetch(devices: unknown, onRequest?: (request: Request) => Response | undefined) {
  return stubFetch((request) => {
    const extra = onRequest?.(request)
    if (extra !== undefined) return extra
    if (new URL(request.url).pathname === '/api/me') return Response.json(PROFILE)
    return Response.json(devices)
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('устройства в MiniApp', () => {
  it('показывает устройство и занятое место в лимите', async () => {
    devicesFetch(ONE_DEVICE)

    renderWithProviders(<Devices />)

    expect(await screen.findByText('iPhone 15')).toBeVisible()
    expect(screen.getByText('Занято 1 из 3')).toBeVisible()
    expect(screen.getByText('iOS · 18.0')).toBeVisible()
  })

  it('только после подтверждения отвязывает устройство с точным hwid', async () => {
    const unlinkRequests: Request[] = []
    devicesFetch(ONE_DEVICE, (request) => {
      if (new URL(request.url).pathname !== '/api/me/devices/unlink') return undefined
      unlinkRequests.push(request)
      return new Response(null, { status: 204 })
    })

    renderWithProviders(<Devices />)
    await userEvent.click(await screen.findByRole('button', { name: 'Отвязать iPhone 15' }))

    const dialog = await screen.findByRole('dialog', { name: 'Отвязать это устройство?' })
    expect(unlinkRequests).toHaveLength(0)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Отвязать' }))

    await waitFor(() => expect(unlinkRequests).toHaveLength(1))
    expect(await unlinkRequests[0]?.json()).toEqual({ hwid: 'hwid-1' })
  })

  it('отменяет отвязку без запроса', async () => {
    const unlinkRequests: Request[] = []
    devicesFetch(ONE_DEVICE, (request) => {
      if (new URL(request.url).pathname !== '/api/me/devices/unlink') return undefined
      unlinkRequests.push(request)
      return new Response(null, { status: 204 })
    })

    renderWithProviders(<Devices />)
    await userEvent.click(await screen.findByRole('button', { name: 'Отвязать iPhone 15' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(unlinkRequests).toHaveLength(0)
  })

  it('объясняет пустой список', async () => {
    devicesFetch({ devices: [], limit: 3, used: 0 })

    renderWithProviders(<Devices />)

    expect(await screen.findByText('Устройств пока нет')).toBeVisible()
  })

  it('показывает ошибку отвязки и сохраняет список', async () => {
    devicesFetch(ONE_DEVICE, (request) => {
      if (new URL(request.url).pathname !== '/api/me/devices/unlink') return undefined
      return Response.json({ error: { code: 'device_not_found' } }, { status: 404 })
    })

    renderWithProviders(<Devices />)
    await userEvent.click(await screen.findByRole('button', { name: 'Отвязать iPhone 15' }))
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Отвязать' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent('Устройство не найдено')
    expect(screen.getByText('iPhone 15')).toBeVisible()
  })

  it('показывает загрузку и даёт повторить запрос списка', async () => {
    withRussianLocale()
    let attempts = 0
    let resolveFirst: ((response: Response) => void) | undefined
    const first = new Promise<Response>((resolve) => {
      resolveFirst = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn((request: Request) => {
        const path = new URL(request.url).pathname
        if (path === '/api/me') return Promise.resolve(Response.json(PROFILE))
        attempts += 1
        if (attempts === 1) return first
        return Promise.resolve(Response.json(ONE_DEVICE))
      }),
    )

    renderWithProviders(<Devices />)
    expect(screen.getByRole('status')).toHaveTextContent('Загрузка')
    resolveFirst?.(Response.json({ error: { code: 'panel_unavailable' } }, { status: 503 }))
    expect(await screen.findByText('Панель устройств сейчас недоступна')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByText('iPhone 15')).toBeVisible()
  })

  it('не выводит внутренний Error вместо локализованной ошибки', async () => {
    withRussianLocale()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (new URL(request.url).pathname === '/api/me') return Response.json(PROFILE)
        throw new Error('raw panel transport details')
      }),
    )

    renderWithProviders(<Devices />)

    expect(await screen.findByText('Что-то пошло не так')).toBeVisible()
    expect(screen.queryByText(/transport details/i)).not.toBeInTheDocument()
  })
})
