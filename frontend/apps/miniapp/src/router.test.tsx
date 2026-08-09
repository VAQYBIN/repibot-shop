import { createMemoryHistory, RouterProvider } from '@tanstack/react-router'
import { act, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { tokenStore } from './api'
import { telegramAuthOptions, useAuthState } from './auth'
import { router } from './router'
import { PROFILE, renderWithProviders } from './test-utils'

const ACTIVE = {
  subscription: {
    plan_code: 'month',
    plan_name: { ru: 'Месяц', en: 'Month' },
    status: 'active',
    started_at: '2026-08-06T12:00:00Z',
    expires_at: '2026-09-05T12:00:00Z',
    subscription_url: 'https://panel.example.org/sub/abc',
    traffic_limit_bytes: 0,
    hwid_device_limit: 3,
  },
  trial_available: false,
}

afterEach(() => {
  vi.unstubAllGlobals()
  tokenStore.set(null)
  useAuthState.setState({ state: 'checking' })
})

describe('защищённые маршруты MiniApp', () => {
  it('ждёт Telegram exchange перед API и после него открывает deep link с навигацией', async () => {
    let resolveExchange: ((response: Response) => void) | undefined
    const exchange = new Promise<Response>((resolve) => {
      resolveExchange = resolve
    })
    const protectedRequests: Request[] = []
    vi.stubGlobal('Telegram', {
      WebApp: {
        initData: 'auth_date=1&hash=abc',
        initDataUnsafe: { user: { language_code: 'ru' } },
      },
    })
    vi.stubGlobal('scrollTo', vi.fn())
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request) => {
        const url = new URL(input instanceof Request ? input.url : input, 'https://miniapp.test')
        if (url.pathname === '/api/auth/telegram/miniapp') return exchange

        const request = input instanceof Request ? input : new Request(url)
        if (url.pathname.startsWith('/api/me')) {
          protectedRequests.push(request)
          if (request.headers.get('Authorization') !== 'Bearer miniapp-token') {
            return new Promise<Response>(() => {})
          }
        }
        if (url.pathname === '/api/me') return Response.json(PROFILE)
        if (url.pathname === '/api/me/subscription') return Response.json(ACTIVE)
        throw new Error(`unexpected request ${url.pathname}`)
      }),
    )
    await act(async () => {
      router.update({
        history: createMemoryHistory({ initialEntries: ['/app/subscription'] }),
      })
      await router.load()
    })

    const signIn = useAuthState.getState().signIn(telegramAuthOptions)
    const view = renderWithProviders(<RouterProvider router={router} />)

    expect(
      (await screen.findAllByRole('status')).some((status) => status.textContent === 'Загрузка'),
    ).toBe(true)
    expect(protectedRequests).toHaveLength(0)

    await act(async () => {
      resolveExchange?.(Response.json({ access_token: 'miniapp-token', expires_in: 900 }))
      await signIn
    })

    expect(await screen.findByRole('heading', { name: 'Месяц' })).toBeVisible()
    expect(protectedRequests).toHaveLength(2)
    expect(
      protectedRequests.every(
        (request) => request.headers.get('Authorization') === 'Bearer miniapp-token',
      ),
    ).toBe(true)
    expect(screen.getByRole('link', { name: 'Подписка' })).toHaveAttribute(
      'href',
      '/app/subscription',
    )
    expect(screen.getByRole('link', { name: 'Устройства' })).toHaveAttribute('href', '/app/devices')
    view.unmount()
  })
})
