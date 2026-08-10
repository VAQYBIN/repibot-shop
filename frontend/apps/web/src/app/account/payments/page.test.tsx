import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import PaymentsPage from './page'

const PLAN = {
  id: 1,
  code: 'month',
  name: { ru: 'Месяц', en: 'Month' },
  description: null,
  duration_days: 30,
  price_rub: '299.00',
  price_stars: 199,
  traffic_limit_bytes: 0,
  hwid_device_limit: 3,
  is_trial: false,
}

const SUBSCRIPTION = {
  subscription: {
    plan_code: 'month',
    plan_name: PLAN.name,
    status: 'active',
    started_at: '2026-08-06T12:00:00Z',
    expires_at: '2026-09-05T12:00:00Z',
    subscription_url: null,
    traffic_limit_bytes: 0,
    hwid_device_limit: 3,
    auto_renew_enabled: false,
  },
  trial_available: false,
}

function handlers(extra: Record<string, unknown> = {}) {
  return {
    '/api/me': { language: 'ru' },
    '/api/plans': [PLAN],
    '/api/me/orders': [],
    '/api/me/gifts': [],
    '/api/me/subscription': SUBSCRIPTION,
    ...extra,
  }
}

afterEach(() => vi.unstubAllGlobals())

describe('оплата в кабинете', () => {
  it('ждёт подписку перед заказом картой и сохраняет выбранное автопродление', async () => {
    let resolveSubscription: ((value: unknown) => void) | undefined
    const delayed = new Promise((resolve) => {
      resolveSubscription = resolve
    })
    let posts = 0
    let body: unknown
    renderWithProviders(<PaymentsPage />, {
      handlers: handlers({
        '/api/me/subscription': () => delayed,
        '/api/me/orders': async (request: Request) => {
          if (request.method === 'GET') return []
          posts += 1
          body = await request.json()
          return {
            id: 17,
            purpose: 'purchase',
            plan_id: 1,
            plan_code: 'month',
            plan_name: PLAN.name,
            duration_days: 30,
            price_rub: '299',
            price_stars: 199,
            gross_rub: '299',
            discount_rub: '0',
            amount_due_rub: '299',
            status: 'pending',
            expires_at: '2026-08-11T12:00:00Z',
            confirmation_url: null,
            telegram_invoice_required: false,
          }
        },
      }),
    })
    const card = await screen.findByRole('button', { name: 'Оплатить картой' })
    expect(card).toBeDisabled()
    await userEvent.click(card)
    expect(posts).toBe(0)
    resolveSubscription?.({
      ...SUBSCRIPTION,
      subscription: { ...SUBSCRIPTION.subscription, auto_renew_enabled: true },
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Оплатить картой' }))
    expect(posts).toBe(1)
    expect(body).toMatchObject({ save_payment_method: true })
  })
  it('просит YooKassa сохранить карту, когда автопродление уже включено', async () => {
    let body: unknown
    renderWithProviders(<PaymentsPage />, {
      handlers: handlers({
        '/api/me/subscription': {
          ...SUBSCRIPTION,
          subscription: { ...SUBSCRIPTION.subscription, auto_renew_enabled: true },
        },
        '/api/me/orders': async (request: Request) => {
          if (request.method === 'GET') return []
          body = await request.json()
          return {
            id: 15,
            purpose: 'renew',
            plan_id: 1,
            plan_code: 'month',
            plan_name: PLAN.name,
            duration_days: 30,
            price_rub: '299',
            price_stars: 199,
            gross_rub: '299',
            discount_rub: '0',
            amount_due_rub: '299',
            status: 'pending',
            expires_at: '2026-08-11T12:00:00Z',
            confirmation_url: null,
            telegram_invoice_required: false,
          }
        },
      }),
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Оплатить картой' }))
    expect(body).toMatchObject({ provider: 'yookassa', save_payment_method: true })
  })
  it('показывает переведённую ошибку отклонённого промокода', async () => {
    renderWithProviders(<PaymentsPage />, {
      handlers: handlers({
        '/api/me/orders': (request: Request) =>
          request.method === 'POST'
            ? { status: 422, body: { error: { code: 'promo_unavailable' } } }
            : [],
      }),
    })
    await userEvent.type(await screen.findByLabelText('Промокод'), 'NOPE')
    await userEvent.click(screen.getByRole('button', { name: 'Оплатить картой' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Промокод недоступен')
  })
  it('показывает загрузку, настоящую ошибку запроса и повторяет его', async () => {
    let attempts = 0
    renderWithProviders(<PaymentsPage />, {
      handlers: handlers({
        '/api/plans': () => {
          attempts += 1
          return attempts === 1
            ? { status: 503, body: { error: { code: 'plan_inactive' } } }
            : [PLAN]
        },
      }),
    })
    expect(screen.getAllByRole('status').length).toBeGreaterThan(0)
    expect(await screen.findByRole('alert')).toHaveTextContent('Этот тариф больше недоступен')
    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByRole('button', { name: 'Оплатить картой' })).toBeVisible()
  })
  it('берёт английские тексты профиля и оставляет действия доступными на узком экране', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 320 })
    renderWithProviders(<PaymentsPage />, { handlers: handlers({ '/api/me': { language: 'en' } }) })
    expect(await screen.findByRole('heading', { name: 'Payments and gifts' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Pay by card' })).toBeVisible()
  })
  it('отправляет промокод, подтверждённый подарок, ваучер и автопродление и показывает состояния заказов', async () => {
    const requests: Request[] = []
    const order = (status: string, id: number) => ({
      id,
      purpose: 'purchase',
      plan_id: 1,
      plan_code: 'month',
      plan_name: PLAN.name,
      duration_days: 30,
      price_rub: '299',
      price_stars: 199,
      gross_rub: '299',
      discount_rub: '0',
      amount_due_rub: '299',
      status,
      expires_at: '2026-08-11T12:00:00Z',
      confirmation_url: null,
      telegram_invoice_required: false,
    })
    renderWithProviders(<PaymentsPage />, {
      handlers: handlers({
        '/api/me/orders': (request: Request) => {
          requests.push(request)
          return request.method === 'POST'
            ? order('pending', 10)
            : [order('pending', 1), order('expired', 2), order('succeeded', 3)]
        },
        '/api/me/gifts': [
          {
            code: 'GIFT-1',
            purchased_at: '2026-08-01T12:00:00Z',
            redeemed_at: null,
            expires_at: '2026-09-01T12:00:00Z',
            purchased_by_me: true,
            redeemed_by_me: false,
          },
        ],
        '/api/me/gifts/redeem': (request: Request) => {
          requests.push(request)
          return SUBSCRIPTION
        },
        '/api/me/subscription/auto-renew': (request: Request) => {
          requests.push(request)
          return { auto_renew_enabled: true }
        },
      }),
    })
    await userEvent.type(await screen.findByLabelText('Промокод'), 'SAVE')
    await userEvent.click(screen.getByRole('button', { name: 'Подарить' }))
    expect(screen.getByRole('dialog', { name: 'Подтвердить подарок?' })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Продолжить' }))
    await userEvent.type(screen.getByLabelText('Код ваучера'), 'GIFT-1')
    await userEvent.click(screen.getByRole('button', { name: 'Активировать ваучер' }))
    await userEvent.click(screen.getByRole('switch', { name: 'Автопродление' }))
    expect(await screen.findByText('Срок оплаты истёк')).toBeVisible()
    expect(screen.getByText('Оплачен')).toBeVisible()
    expect(screen.getByText('Подарочный ваучер').parentElement).toHaveTextContent('GIFT-1')
    const bodies = await Promise.all(
      requests.filter((request) => request.method !== 'GET').map((request) => request.json()),
    )
    expect(bodies).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ purpose: 'gift', promo_code: 'SAVE' }),
        { code: 'GIFT-1' },
        { auto_renew_enabled: true },
      ]),
    )
  })
  it('открывает именно ту передачу в Stars, которую вернул сервер', async () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)
    renderWithProviders(<PaymentsPage />, {
      handlers: handlers({
        '/api/me/orders': (request: Request) =>
          request.method === 'POST'
            ? {
                id: 11,
                purpose: 'purchase',
                plan_id: 1,
                plan_code: 'month',
                plan_name: PLAN.name,
                duration_days: 30,
                price_rub: '299',
                price_stars: 199,
                gross_rub: '299',
                discount_rub: '0',
                amount_due_rub: '299',
                status: 'pending',
                expires_at: '2026-08-11T12:00:00Z',
                confirmation_url: null,
                telegram_invoice_required: true,
                telegram_handoff_url: 'https://t.me/repibot?start=order_11',
              }
            : [],
      }),
    })
    await userEvent.click(await screen.findByRole('button', { name: /оплатить stars/i }))
    expect(open).toHaveBeenCalledWith(
      'https://t.me/repibot?start=order_11',
      '_blank',
      'noopener,noreferrer',
    )
  })
  it('открывает ссылку YooKassa только после того, как сервер создал заказ', async () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)
    renderWithProviders(<PaymentsPage />, {
      handlers: handlers({
        '/api/me/orders': (request: Request) =>
          request.method === 'POST'
            ? {
                id: 10,
                purpose: 'purchase',
                plan_id: 1,
                plan_code: 'month',
                plan_name: PLAN.name,
                duration_days: 30,
                price_rub: '299.00',
                price_stars: 199,
                gross_rub: '299.00',
                discount_rub: '0.00',
                amount_due_rub: '299.00',
                status: 'pending',
                expires_at: '2026-08-11T12:00:00Z',
                confirmation_url: 'https://yookassa.test/confirm',
                telegram_invoice_required: false,
              }
            : [],
      }),
    })

    await userEvent.click(await screen.findByRole('button', { name: /оплатить картой/i }))

    expect(open).toHaveBeenCalledWith(
      'https://yookassa.test/confirm',
      '_blank',
      'noopener,noreferrer',
    )
  })
})
