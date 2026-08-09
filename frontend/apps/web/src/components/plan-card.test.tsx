import type { Language } from '@repibot/core'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { type Plan, PlanCard } from './plan-card'

const PLAN: Plan = {
  id: 1,
  code: 'month',
  name: { ru: 'Месяц', en: 'Month' },
  description: null,
  duration_days: 30,
  price_rub: '299.00',
  price_stars: 1,
  traffic_limit_bytes: 0,
  hwid_device_limit: 3,
  is_trial: false,
}

function renderedStars(language: Language, amount: number): string {
  render(<PlanCard plan={{ ...PLAN, price_stars: amount }} language={language} />)
  const price = screen.getByText(/звезд|звёзд|звезды|звезда|stars?/i)
  // Intl использует locale-specific NBSP/narrow NBSP. Для текста значима
  // группировка, но не конкретный Unicode-код пробела.
  return price.textContent?.replace(/\s+/gu, ' ').trim() ?? ''
}

describe('цена тарифа в Stars', () => {
  it.each([
    [1, '1 звезда'],
    [2, '2 звезды'],
    [5, '5 звёзд'],
    [1000, '1 000 звёзд'],
    [10_000, '10 000 звёзд'],
  ] as const)('форматирует %i по-русски как «%s»', (amount, expected) => {
    expect(renderedStars('ru', amount)).toBe(expected)
  })

  it.each([
    [1, '1 star'],
    [2, '2 stars'],
    [1000, '1,000 stars'],
  ] as const)('форматирует %i по-английски как «%s»', (amount, expected) => {
    expect(renderedStars('en', amount)).toBe(expected)
  })
})
