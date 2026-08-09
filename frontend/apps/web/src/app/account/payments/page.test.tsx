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
  it('sends promo, confirmed gift, voucher and auto-renew intents to the server and renders order states', async () => {
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
        '/api/me/gifts/redeem': SUBSCRIPTION,
        '/api/me/subscription/auto-renew': { auto_renew_enabled: true },
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
  it('opens the specific Stars handoff returned by the server', async () => {
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
  it('opens a confirmed YooKassa URL only after server creates an order', async () => {
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
