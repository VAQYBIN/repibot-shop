import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import HomePage from './page'

const fetchFromApi = vi.fn()

vi.mock('@/lib/server-api', () => ({ fetchFromApi: (path: string) => fetchFromApi(path) }))
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

beforeEach(() => fetchFromApi.mockReset())

describe('главная', () => {
  it('собирает страницу из тарифов, полученных на сервере', async () => {
    fetchFromApi.mockResolvedValue([month, { ...month, id: 2, code: 'trial', is_trial: true }])

    render(await HomePage())

    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    expect(screen.getByText('карточка month')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'landing.hero.cta_trial' })).toBeInTheDocument()
  })

  it('открывается, даже когда API недоступен', async () => {
    fetchFromApi.mockResolvedValue(null)

    render(await HomePage())

    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    expect(screen.getByText('landing.plans.unavailable')).toBeInTheDocument()
    // Без данных обещать пробный период нельзя: неизвестно, включён ли он.
    expect(screen.queryByRole('link', { name: 'landing.hero.cta_trial' })).not.toBeInTheDocument()
  })
})
