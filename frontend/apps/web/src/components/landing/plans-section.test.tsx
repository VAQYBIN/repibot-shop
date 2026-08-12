import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LandingPlans } from './plans-section'

vi.mock('@repibot/core', () => ({ translate: (_: string, key: string) => key }))
vi.mock('@/components/plan-card', () => ({
  PlanCard: ({ plan }: { plan: { code: string } }) => <div>карточка {plan.code}</div>,
}))

const month = {
  id: 1,
  code: 'month',
  name: { ru: 'Месяц', en: 'Month' },
  description: null,
  duration_days: 30,
  price_rub: '299.00',
  price_stars: 300,
  traffic_limit_bytes: 0,
  hwid_device_limit: 3,
  is_trial: false,
}

const trial = { ...month, id: 2, code: 'trial', is_trial: true }

describe('тарифы на главной', () => {
  it('показывает продаваемые тарифы и не показывает пробный', () => {
    render(<LandingPlans plans={[month, trial]} />)

    expect(screen.getByText('карточка month')).toBeInTheDocument()
    expect(screen.queryByText('карточка trial')).not.toBeInTheDocument()
  })

  it('переживает недоступный API и уводит на страницу тарифов', () => {
    render(<LandingPlans plans={null} />)

    expect(screen.getByText('landing.plans.unavailable')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'landing.plans.all' })).toHaveAttribute(
      'href',
      '/plans',
    )
  })
})
