import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import Page from './page'

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

const DEVICES = {
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

const TRAFFIC = {
  used_bytes: 1_073_741_824,
  lifetime_bytes: 2_147_483_648,
  limit_bytes: 10_737_418_240,
  days: [{ day: '2026-08-06', used_bytes: 268_435_456 }],
}

function fullHandlers(extra: Record<string, unknown> = {}) {
  return {
    '/api/me/subscription': ACTIVE,
    '/api/me/devices': DEVICES,
    '/api/me/traffic': TRAFFIC,
    ...extra,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('подписка в кабинете', () => {
  it('показывает активное состояние, дату, ссылку и локальный QR-код', async () => {
    const requests: string[] = []
    renderWithProviders(<Page />, {
      handlers: {
        '/api/me/subscription': (request: Request) => {
          requests.push(request.url)
          return ACTIVE
        },
        '/api/me/devices': (request: Request) => {
          requests.push(request.url)
          return DEVICES
        },
        '/api/me/traffic': (request: Request) => {
          requests.push(request.url)
          return TRAFFIC
        },
      },
    })

    expect(await screen.findByText('Месяц')).toBeVisible()
    expect(screen.getByText('Активна')).toBeVisible()
    expect(screen.getByText('Действует до')).toBeVisible()
    expect(screen.getByRole('link', { name: ACTIVE.subscription.subscription_url })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Скопировать' })).toBeVisible()
    expect(await screen.findByRole('img', { name: 'QR-код' })).toContainHTML('<svg')
    expect(requests.every((url) => new URL(url).origin === 'http://api.test')).toBe(true)
  })

  it('копирует ссылку и сообщает об успехе', async () => {
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal('navigator', {
      language: navigator.language,
      languages: navigator.languages,
      clipboard: { writeText },
    })
    renderWithProviders(<Page />, { handlers: fullHandlers() })

    await userEvent.click(await screen.findByRole('button', { name: 'Скопировать' }))

    expect(writeText).toHaveBeenCalledWith(ACTIVE.subscription.subscription_url)
    expect(await screen.findByRole('status')).toHaveTextContent('Скопировано')
  })

  it('объясняет ожидание вместо пустого экрана', async () => {
    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/subscription': {
          subscription: {
            ...ACTIVE.subscription,
            status: 'pending_provision',
            subscription_url: null,
          },
          trial_available: false,
        },
      }),
    })

    expect(await screen.findByText('Выдаём доступ')).toBeVisible()
    expect(screen.getByText('Доступ появится через несколько минут')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Скопировать' })).not.toBeInTheDocument()
  })

  it.each([
    ['trial', 'Пробный период'],
    ['expired', 'Истекла'],
    ['disabled', 'Отключена'],
  ])('показывает отдельное состояние %s', async (status, label) => {
    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/subscription': {
          subscription: { ...ACTIVE.subscription, status, subscription_url: null },
          trial_available: false,
        },
      }),
    })

    expect(await screen.findByText(label)).toBeVisible()
  })

  it('активирует триал, пока он доступен', async () => {
    let activated = false
    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/subscription': { subscription: null, trial_available: true },
        '/api/me/subscription/trial': (request: Request) => {
          activated = request.method === 'POST'
          return ACTIVE
        },
      }),
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Попробовать бесплатно' }))

    expect(activated).toBe(true)
    expect(await screen.findByText('Месяц')).toBeVisible()
  })

  it('не предлагает триал, если право уже использовано', async () => {
    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/subscription': { subscription: null, trial_available: false },
      }),
    })

    expect(await screen.findByText('Подписки пока нет')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Попробовать бесплатно' })).not.toBeInTheDocument()
  })

  it('сохраняет подписку и трафик, когда устройства недоступны', async () => {
    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/devices': {
          status: 503,
          body: { error: { code: 'panel_unavailable' } },
        },
      }),
    })

    expect(await screen.findByText('Месяц')).toBeVisible()
    expect(screen.getByText('Использовано')).toBeVisible()
    const devices = screen.getByRole('region', { name: 'Устройства' })
    expect(within(devices).getByRole('alert')).toHaveTextContent(
      'Панель устройств сейчас недоступна',
    )
  })

  it('сохраняет подписку и устройства, когда трафик недоступен', async () => {
    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/traffic': {
          status: 503,
          body: { error: { code: 'panel_unavailable' } },
        },
      }),
    })

    expect(await screen.findByText('Месяц')).toBeVisible()
    expect(screen.getByText('iPhone 15')).toBeVisible()
    const traffic = screen.getByRole('region', { name: 'Трафик' })
    expect(within(traffic).getByRole('alert')).toHaveTextContent(
      'Панель устройств сейчас недоступна',
    )
  })

  it('спрашивает подтверждение и только затем отвязывает нужное устройство', async () => {
    const unlinkRequests: Request[] = []
    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/devices/unlink': (request: Request) => {
          unlinkRequests.push(request)
          return { status: 204, body: undefined }
        },
      }),
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Отвязать iPhone 15' }))
    const dialog = await screen.findByRole('dialog', { name: 'Отвязать это устройство?' })
    expect(unlinkRequests).toHaveLength(0)

    await userEvent.click(within(dialog).getByRole('button', { name: 'Отвязать' }))

    await waitFor(() => expect(unlinkRequests).toHaveLength(1))
    expect(await unlinkRequests[0]?.json()).toEqual({ hwid: 'hwid-1' })
  })

  it('показывает пустой список устройств и безлимитный трафик', async () => {
    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/devices': { devices: [], limit: 3, used: 0 },
        '/api/me/traffic': { ...TRAFFIC, limit_bytes: 0 },
      }),
    })

    expect(await screen.findByText('Устройств пока нет')).toBeVisible()
    expect(screen.getByText(/Безлимитный/)).toBeVisible()
  })

  it('показывает загрузку, а отказ подписки — как доступную ошибку', async () => {
    let resolveSubscription: ((value: unknown) => void) | undefined
    const subscription = new Promise((resolve) => {
      resolveSubscription = resolve
    })
    const view = renderWithProviders(<Page />, {
      handlers: fullHandlers({ '/api/me/subscription': () => subscription }),
    })

    expect(screen.getAllByRole('status').some((status) => status.textContent === 'Загрузка')).toBe(
      true,
    )
    view.unmount()
    resolveSubscription?.(ACTIVE)

    renderWithProviders(<Page />, {
      handlers: fullHandlers({
        '/api/me/subscription': {
          status: 503,
          body: { error: { code: 'panel_unavailable' } },
        },
      }),
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('Панель устройств сейчас недоступна')
  })
})
