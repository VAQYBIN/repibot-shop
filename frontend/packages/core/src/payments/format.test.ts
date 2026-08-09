import { describe, expect, it } from 'vitest'

import { formatOrderAmount, formatPaymentStatus } from './format'

const ORDER = {
  id: 41,
  purpose: 'purchase',
  plan_id: 2,
  plan_code: 'month',
  plan_name: { ru: 'Месяц', en: 'Month' },
  duration_days: 30,
  price_rub: '299.00',
  price_stars: 199,
  gross_rub: '299.00',
  discount_rub: '0.00',
  amount_due_rub: '254.15',
  status: 'pending',
  expires_at: '2026-09-05T12:00:00Z',
  confirmation_url: 'https://pay.example.test/41',
  telegram_invoice_required: false,
  telegram_handoff_url: null,
} as const

describe('formatOrderAmount', () => {
  it('formats the amount due returned by the YooKassa order', () => {
    // Replacing amount_due_rub with gross_rub would make the paid amount wrong
    // whenever the API applies a promotion.
    expect(formatOrderAmount(ORDER, 'ru')).toBe('254,15 ₽')
    expect(formatOrderAmount(ORDER, 'en')).toBe('RUB 254.15')
  })

  it('uses Stars data from the response when Telegram must issue an invoice', () => {
    expect(formatOrderAmount({ ...ORDER, telegram_invoice_required: true }, 'ru')).toBe('199 звёзд')
    expect(formatOrderAmount({ ...ORDER, telegram_invoice_required: true }, 'en')).toBe('199 stars')
  })
})

describe('formatPaymentStatus', () => {
  it.each([
    ['pending', 'ru', 'Ожидает оплаты'],
    ['fulfilled', 'en', 'Paid'],
    ['expired', 'ru', 'Срок оплаты истёк'],
    ['canceled', 'en', 'Cancelled'],
    ['refunded', 'ru', 'Возвращён'],
  ] as const)('localizes the %s status from an order response', (status, language, expected) => {
    expect(formatPaymentStatus({ ...ORDER, status }, language)).toBe(expected)
  })

  it('does not invent a success status for an unknown response status', () => {
    expect(formatPaymentStatus({ ...ORDER, status: 'provider_pending' }, 'en')).toBe(
      'Payment pending',
    )
  })
})
