import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PROFILE, renderWithProviders, stubFetch, withRussianLocale } from '../test-utils'
import { Subscription } from './subscription'

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

function subscriptionFetch(
  subscription: unknown,
  onRequest?: (request: Request) => Response | undefined,
) {
  return stubFetch((request) => {
    const extra = onRequest?.(request)
    if (extra !== undefined) return extra
    if (new URL(request.url).pathname === '/api/me') return Response.json(PROFILE)
    return Response.json(subscription)
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('подписка в MiniApp', () => {
  it('показывает тариф, срок и копирует ссылку без QR-кода', async () => {
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal('navigator', {
      language: navigator.language,
      languages: navigator.languages,
      clipboard: { writeText },
    })
    subscriptionFetch(ACTIVE)

    renderWithProviders(<Subscription />)

    expect(await screen.findByRole('heading', { name: 'Месяц' })).toBeVisible()
    expect(screen.getByText('Действует до')).toBeVisible()
    expect(screen.getByRole('link', { name: ACTIVE.subscription.subscription_url })).toBeVisible()
    expect(screen.queryByText(/QR/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Скопировать' }))

    expect(writeText).toHaveBeenCalledWith(ACTIVE.subscription.subscription_url)
    expect(await screen.findByRole('status')).toHaveTextContent('Скопировано')
  })

  it('объясняет ожидание выдачи, а не показывает пустоту', async () => {
    subscriptionFetch({
      subscription: {
        ...ACTIVE.subscription,
        status: 'pending_provision',
        subscription_url: null,
      },
      trial_available: false,
    })

    renderWithProviders(<Subscription />)

    expect(await screen.findByText('Выдаём доступ')).toBeVisible()
    expect(screen.getByText('Доступ появится через несколько минут')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Скопировать' })).not.toBeInTheDocument()
  })

  it('активирует триал, пока он доступен', async () => {
    const requests: Request[] = []
    subscriptionFetch({ subscription: null, trial_available: true }, (request) => {
      if (new URL(request.url).pathname !== '/api/me/subscription/trial') return undefined
      requests.push(request)
      return Response.json(ACTIVE)
    })

    renderWithProviders(<Subscription />)
    await userEvent.click(await screen.findByRole('button', { name: 'Попробовать бесплатно' }))

    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    expect(await screen.findByRole('heading', { name: 'Месяц' })).toBeVisible()
  })

  it('показывает пустое состояние без ложного предложения триала', async () => {
    subscriptionFetch({ subscription: null, trial_available: false })

    renderWithProviders(<Subscription />)

    expect(await screen.findByText('Подписки пока нет')).toBeVisible()
    expect(screen.queryByRole('button', { name: /\u043fопробовать/i })).not.toBeInTheDocument()
  })

  it('показывает загрузку и даёт повторить запрос после ошибки', async () => {
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
        return Promise.resolve(Response.json(ACTIVE))
      }),
    )

    const view = renderWithProviders(<Subscription />)
    expect(screen.getByRole('status')).toHaveTextContent('Загрузка')
    resolveFirst?.(Response.json({ error: { code: 'panel_unavailable' } }, { status: 503 }))
    expect(await screen.findByText('Панель устройств сейчас недоступна')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByRole('heading', { name: 'Месяц' })).toBeVisible()
    view.unmount()
  })
})
