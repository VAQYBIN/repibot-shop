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
  it('hands Stars payment to the bot instead of opening a browser settlement', async () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)
    stubFetch((request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/me') return Response.json(PROFILE)
      if (path === '/api/plans') return Response.json([PLAN])
      if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
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
  })
})
