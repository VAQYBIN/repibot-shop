import { act, fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PurchaseNotice } from './purchase-notice'
import { PROFILE, renderWithProviders, stubFetch } from './test-utils'

const ORDER = {
  id: 7,
  purpose: 'purchase',
  plan_id: 2,
  plan_code: 'check',
  plan_name: { ru: 'Проверка', en: 'Check' },
  duration_days: 1,
  price_rub: '1.00',
  price_stars: 1,
  gross_rub: '1.00',
  discount_rub: '0.00',
  amount_due_rub: '1.00',
  status: 'pending',
  expires_at: '2100-01-01T00:00:00Z',
  confirmation_url: null,
  telegram_invoice_required: false,
  telegram_handoff_url: null,
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

/** Заказ, статус которого меняет сам тест: провайдер отвечает не сразу. */
function stubOrders(order: Record<string, unknown>) {
  stubFetch((request) => {
    const path = new URL(request.url).pathname
    if (path === '/api/me') return Response.json(PROFILE)
    if (path === '/api/me/orders') return Response.json([order])
    return new Response(null, { status: 404 })
  })
}

describe('окно об оплаченном заказе', () => {
  it('дожидается выдачи и показывает, что подписка активирована', async () => {
    /* Оплату подтверждает вебхук провайдера, а доступ выдаёт очередь: в
       момент возвращения человека новостей ещё нет, и без ожидания экран
       остался бы с неоплаченным заказом. */
    const order = { ...ORDER }
    stubOrders(order)
    vi.useFakeTimers()

    renderWithProviders(<PurchaseNotice />, 30_000)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    order.status = 'fulfilled'
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4100)
    })

    const dialog = screen.getByRole('dialog', { name: 'Оплата прошла' })
    expect(dialog).toBeVisible()
    expect(dialog).toHaveTextContent('Подписка активирована')
  })

  it('называет продление продлением, а не покупкой', async () => {
    const order = { ...ORDER, purpose: 'renew' }
    stubOrders(order)
    vi.useFakeTimers()

    renderWithProviders(<PurchaseNotice />, 30_000)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    order.status = 'fulfilled'
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4100)
    })

    expect(screen.getByRole('dialog')).toHaveTextContent('Подписка продлена')
  })

  it('молчит о заказе, выданном до открытия приложения', async () => {
    /* Иначе окно всплывало бы при каждом входе и рассказывало о покупке,
       про которую человек давно знает. */
    stubOrders({ ...ORDER, status: 'fulfilled' })
    vi.useFakeTimers()

    renderWithProviders(<PurchaseNotice />, 30_000)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('закрывается по кнопке', async () => {
    const order = { ...ORDER }
    stubOrders(order)
    vi.useFakeTimers()

    renderWithProviders(<PurchaseNotice />, 30_000)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    order.status = 'fulfilled'
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4100)
    })
    expect(screen.getByRole('dialog')).toBeVisible()

    // fireEvent, а не userEvent: тот ждёт настоящие таймеры, а здесь они
    // подменены — иначе клик не дождётся сам себя.
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Закрыть' }))
    })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
