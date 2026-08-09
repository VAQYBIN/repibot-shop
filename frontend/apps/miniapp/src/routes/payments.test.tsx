import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PROFILE, renderWithProviders, stubFetch } from '../test-utils'
import { Payments } from './payments'

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

afterEach(() => vi.unstubAllGlobals())

describe('оплата в Mini App', () => {
  it('requires confirmation before a Mini App gift sends purpose=gift', async () => {
    const requests: Request[] = []
    stubFetch((request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/me') return Response.json(PROFILE)
      if (path === '/api/plans') return Response.json([PLAN])
      if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
      if (path === '/api/me/gifts') return Response.json([])
      if (path === '/api/me/subscription')
        return Response.json({ subscription: null, trial_available: false })
      requests.push(request)
      return Response.json({
        id: 13,
        purpose: 'gift',
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
        confirmation_url: 'https://yookassa.test/gift',
        telegram_invoice_required: false,
      })
    })
    renderWithProviders(<Payments />)
    await userEvent.click(await screen.findByRole('button', { name: 'Подарить' }))
    expect(screen.getByRole('dialog', { name: 'Подтвердить подарок?' })).toBeVisible()
    expect(requests).toHaveLength(0)
    await userEvent.click(screen.getByRole('button', { name: 'Продолжить' }))
    expect(await requests[0]?.json()).toMatchObject({ purpose: 'gift', provider: 'yookassa' })
  })
  it('hands the server confirmation URL to Telegram for a card order', async () => {
    const openLink = vi.fn()
    vi.stubGlobal('Telegram', { WebApp: { openLink } })
    stubFetch((request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/me') return Response.json(PROFILE)
      if (path === '/api/plans') return Response.json([PLAN])
      if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
      if (path === '/api/me/gifts') return Response.json([])
      if (path === '/api/me/subscription')
        return Response.json({ subscription: null, trial_available: false })
      return Response.json({
        id: 12,
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
      })
    })
    renderWithProviders(<Payments />)
    await userEvent.click(await screen.findByRole('button', { name: /оплатить картой/i }))
    expect(openLink).toHaveBeenCalledWith('https://yookassa.test/confirm')
  })
  it('hands Stars payment to the bot instead of opening a browser settlement', async () => {
    const open = vi.fn()
    const openTelegramLink = vi.fn()
    vi.stubGlobal('open', open)
    vi.stubGlobal('Telegram', { WebApp: { openTelegramLink } })
    stubFetch((request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/me') return Response.json(PROFILE)
      if (path === '/api/plans') return Response.json([PLAN])
      if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
      if (path === '/api/me/gifts') return Response.json([])
      if (path === '/api/me/subscription')
        return Response.json({ subscription: null, trial_available: false })
      if (path === '/api/me/orders') {
        return Response.json({
          id: 11,
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
          confirmation_url: null,
          telegram_invoice_required: true,
          telegram_handoff_url: 'https://t.me/repibot?start=order_11',
        })
      }
      return new Response(null, { status: 404 })
    })

    renderWithProviders(<Payments />)
    await userEvent.click(await screen.findByRole('button', { name: /оплатить stars/i }))

    expect(await screen.findByText(/счёт в telegram stars выставит бот/i)).toBeVisible()
    expect(open).not.toHaveBeenCalled()
    expect(openTelegramLink).toHaveBeenCalledWith('https://t.me/repibot?start=order_11')
  })
})
