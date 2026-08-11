import { focusManager } from '@tanstack/react-query'
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { trackTelegramActivity } from '../activity'
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

const SUBSCRIPTION = {
  plan_code: 'month',
  plan_name: PLAN.name,
  status: 'active',
  started_at: '2026-08-01T12:00:00Z',
  expires_at: '2026-09-01T12:00:00Z',
  subscription_url: null,
  traffic_limit_bytes: 0,
  hwid_device_limit: 3,
  auto_renew_enabled: false,
}

const NO_CARD = { title: null, linked_at: null, binding_available: false }

interface PaymentMethod {
  title: string | null
  linked_at: string | null
  binding_available: boolean
}

/**
 * Общие ответы экрана оплаты. Возвращает `null`, если путь не разобран, —
 * тогда тест сам решает, чем ответить, и заодно видит запрос.
 */
function paymentHandlers(card: PaymentMethod, subscription: unknown = SUBSCRIPTION) {
  return (request: Request): Response | null => {
    const path = new URL(request.url).pathname
    if (path === '/api/me') return Response.json(PROFILE)
    if (path === '/api/plans') return Response.json([PLAN])
    if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
    if (path === '/api/me/gifts') return Response.json([])
    if (path === '/api/me/subscription')
      return Response.json({ subscription, trial_available: false })
    if (path === '/api/me/payment-method' && request.method === 'GET') return Response.json(card)
    return null
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
  // Признак активности глобальный: без сброса он утёк бы в следующий тест.
  focusManager.setFocused(undefined)
})

describe('оплата в Mini App', () => {
  it('не решает за плательщика, запоминать ли карту', async () => {
    let body: unknown
    stubFetch((request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/me') return Response.json(PROFILE)
      if (path === '/api/plans') return Response.json([PLAN])
      if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
      if (path === '/api/me/gifts') return Response.json([])
      if (path === '/api/me/payment-method') return Response.json(NO_CARD)
      if (path === '/api/me/subscription')
        return Response.json({
          subscription: {
            plan_code: 'month',
            plan_name: PLAN.name,
            status: 'active',
            started_at: '2026-08-01T12:00:00Z',
            expires_at: '2026-09-01T12:00:00Z',
            subscription_url: null,
            traffic_limit_bytes: 0,
            hwid_device_limit: 3,
            auto_renew_enabled: true,
          },
          trial_available: false,
        })
      void request.json().then((value) => {
        body = value
      })
      return Response.json({
        id: 16,
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
      })
    })
    renderWithProviders(<Payments />)
    await userEvent.click(await screen.findByRole('button', { name: 'Оплатить картой' }))
    // Галочку «запомнить карту» показывает форма YooKassa; прислать флаг
    // значит запомнить карту без согласия плательщика.
    await waitFor(() => expect(body).toMatchObject({ provider: 'yookassa' }))
    expect(body).not.toHaveProperty('save_payment_method')
  })
  it('закрывает подтверждение подарка, чтобы второе «Продолжить» не создало второй заказ', async () => {
    const posts: Request[] = []
    stubFetch((request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/me') return Response.json(PROFILE)
      if (path === '/api/plans') return Response.json([PLAN])
      if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
      if (path === '/api/me/gifts') return Response.json([])
      if (path === '/api/me/payment-method') return Response.json(NO_CARD)
      if (path === '/api/me/subscription')
        return Response.json({ subscription: null, trial_available: false })
      posts.push(request)
      return Response.json({
        id: 14,
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
        confirmation_url: null,
        telegram_invoice_required: false,
      })
    })
    renderWithProviders(<Payments />)
    await userEvent.click(await screen.findByRole('button', { name: 'Подарить' }))
    await userEvent.click(screen.getByRole('button', { name: 'Продолжить' }))
    expect(await screen.findByRole('heading', { name: 'Оплата и подарки' })).toBeVisible()
    expect(screen.queryByRole('dialog', { name: 'Подтвердить подарок?' })).not.toBeInTheDocument()
    expect(posts).toHaveLength(1)
  })
  it('требует подтверждения, прежде чем отправить purpose=gift', async () => {
    const requests: Request[] = []
    stubFetch((request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/me') return Response.json(PROFILE)
      if (path === '/api/plans') return Response.json([PLAN])
      if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
      if (path === '/api/me/gifts') return Response.json([])
      if (path === '/api/me/payment-method') return Response.json(NO_CARD)
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
  it('отдаёт Telegram серверную ссылку оплаты для заказа картой', async () => {
    const openLink = vi.fn()
    vi.stubGlobal('Telegram', { WebApp: { openLink } })
    stubFetch((request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/me') return Response.json(PROFILE)
      if (path === '/api/plans') return Response.json([PLAN])
      if (path === '/api/me/orders' && request.method === 'GET') return Response.json([])
      if (path === '/api/me/gifts') return Response.json([])
      if (path === '/api/me/payment-method') return Response.json(NO_CARD)
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
  it('отдаёт оплату Stars боту, а не открывает расчёт в браузере', async () => {
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
      if (path === '/api/me/payment-method') return Response.json(NO_CARD)
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

describe('карта для автоплатежа в Mini App', () => {
  it('не даёт включить автопродление, пока карты нет', async () => {
    const base = paymentHandlers(NO_CARD)
    stubFetch((request) => base(request) ?? new Response(null, { status: 404 }))

    renderWithProviders(<Payments />)

    expect(await screen.findByText('Карта не привязана')).toBeVisible()
    expect(
      screen.getByText(/Карта запоминается, только если отметить «запомнить карту»/),
    ).toBeVisible()
    const toggle = await screen.findByRole('switch', { name: 'Автопродление' })
    expect(toggle).toBeDisabled()
    expect(toggle).not.toBeChecked()
  })

  it('показывает название карты из ответа сервера, а не собирает его сам', async () => {
    const base = paymentHandlers({
      title: 'MasterCard •••• 4444',
      linked_at: '2026-08-01T12:00:00Z',
      binding_available: true,
    })
    stubFetch((request) => base(request) ?? new Response(null, { status: 404 }))

    renderWithProviders(<Payments />)

    expect(await screen.findByText('MasterCard •••• 4444')).toBeVisible()
    expect(screen.queryByText('Карта не привязана')).not.toBeInTheDocument()
    const toggle = await screen.findByRole('switch', { name: 'Автопродление' })
    expect(toggle).toBeEnabled()
  })

  it('не отвязывает карту, пока отвязку не подтвердили', async () => {
    const base = paymentHandlers({
      title: 'MasterCard •••• 4444',
      linked_at: '2026-08-01T12:00:00Z',
      binding_available: false,
    })
    const requests: Request[] = []
    stubFetch((request) => {
      const handled = base(request)
      if (handled !== null) return handled
      requests.push(request)
      return new Response(null, { status: 204 })
    })

    renderWithProviders(<Payments />)

    await userEvent.click(await screen.findByRole('button', { name: /Отвязать карту MasterCard/ }))
    expect(screen.getByRole('dialog', { name: 'Отвязать карту?' })).toBeVisible()
    expect(requests).toHaveLength(0)

    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Отвязать карту' }),
    )
    await waitFor(() => expect(requests).toHaveLength(1))
    expect(requests[0]?.method).toBe('DELETE')
    expect(new URL(requests[0]?.url ?? '').pathname).toBe('/api/me/payment-method')
  })

  it('прячет привязку карты, когда сервер её не разрешает', async () => {
    const base = paymentHandlers({
      title: 'MasterCard •••• 4444',
      linked_at: '2026-08-01T12:00:00Z',
      binding_available: false,
    })
    stubFetch((request) => base(request) ?? new Response(null, { status: 404 }))

    renderWithProviders(<Payments />)

    expect(await screen.findByText('MasterCard •••• 4444')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Привязать другую' })).not.toBeInTheDocument()
  })

  it('называет серверу Mini App, чтобы провайдер вернул плательщика в Telegram', async () => {
    vi.stubGlobal('Telegram', { WebApp: { openLink: vi.fn() } })
    const base = paymentHandlers({ ...NO_CARD, binding_available: true })
    const requests: Request[] = []
    stubFetch((request) => {
      const handled = base(request)
      if (handled !== null) return handled
      requests.push(request)
      if (new URL(request.url).pathname === '/api/me/payment-method/bindings')
        return Response.json({ confirmation_url: 'https://yookassa.test/bind' })
      return Response.json({
        id: 19,
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
    await userEvent.click(await screen.findByRole('button', { name: 'Оплатить картой' }))
    await userEvent.click(screen.getByRole('button', { name: 'Привязать другую' }))

    await waitFor(() => expect(requests).toHaveLength(2))
    // Вернуть из Mini App на страницу сайта значит высадить человека туда, где
    // вход невозможен: initData есть только внутри Telegram. Поверхность здесь
    // всегда своя, а конечный адрес возврата выбирает сервер.
    const bodies = await Promise.all(requests.map((request) => request.json()))
    expect(bodies).toEqual([
      expect.objectContaining({ return_surface: 'miniapp' }),
      { return_surface: 'miniapp' },
    ])
  })

  it('показывает карту сразу после возвращения с формы привязки', async () => {
    /* Тот самый разрыв: `openLink` не закрывает Mini App, а сворачивает его,
       и без пересказа события Telegram экран остался бы со снимком «карты
       нет» до тех пор, пока человек не уйдёт на другую вкладку и не вернётся. */
    const handlers = new Map<string, () => void>()
    const openLink = vi.fn()
    vi.stubGlobal('Telegram', {
      WebApp: {
        openLink,
        onEvent: (event: string, handler: () => void) => handlers.set(event, handler),
        offEvent: (event: string) => handlers.delete(event),
      },
    })
    trackTelegramActivity()
    const card: PaymentMethod = { ...NO_CARD, binding_available: true }
    const base = paymentHandlers(card)
    stubFetch((request) => {
      const handled = base(request)
      if (handled !== null) return handled
      if (new URL(request.url).pathname === '/api/me/payment-method/bindings')
        return Response.json({ confirmation_url: 'https://yookassa.test/bind' })
      return new Response(null, { status: 404 })
    })

    renderWithProviders(<Payments />, 30_000)

    await userEvent.click(await screen.findByRole('button', { name: 'Привязать другую' }))
    await waitFor(() => expect(openLink).toHaveBeenCalledWith('https://yookassa.test/bind'))
    // Пока приложение свёрнуто, привязку подтверждает провайдер.
    card.title = 'MasterCard •••• 4444'
    card.linked_at = '2026-08-01T12:00:00Z'
    act(() => handlers.get('deactivated')?.())
    act(() => handlers.get('activated')?.())

    expect(await screen.findByText('MasterCard •••• 4444')).toBeVisible()
  })

  it('отдаёт Telegram ссылку подтверждения привязки, а не открывает вкладку', async () => {
    const open = vi.fn()
    const openLink = vi.fn()
    vi.stubGlobal('open', open)
    vi.stubGlobal('Telegram', { WebApp: { openLink } })
    const base = paymentHandlers({ ...NO_CARD, binding_available: true })
    stubFetch((request) => {
      const handled = base(request)
      if (handled !== null) return handled
      if (new URL(request.url).pathname === '/api/me/payment-method/bindings')
        return Response.json({ confirmation_url: 'https://yookassa.test/bind' })
      return new Response(null, { status: 404 })
    })

    renderWithProviders(<Payments />)

    await userEvent.click(await screen.findByRole('button', { name: 'Привязать другую' }))
    await waitFor(() => expect(openLink).toHaveBeenCalledWith('https://yookassa.test/bind'))
    expect(open).not.toHaveBeenCalled()
  })
})
