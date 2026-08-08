import { screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import Page from './page'

const paidPlan = {
  id: 1,
  code: 'month',
  name: { ru: 'Месяц', en: 'Month' },
  description: { ru: 'Доступ на месяц', en: 'One month of access' },
  duration_days: 30,
  price_rub: '299.00',
  price_stars: 199,
  traffic_limit_bytes: 0,
  hwid_device_limit: 3,
  is_trial: false,
} as const

const trialPlan = {
  id: 2,
  code: 'trial',
  name: { ru: 'Пробный период', en: 'Trial' },
  description: null,
  duration_days: 3,
  price_rub: '0.00',
  price_stars: 0,
  traffic_limit_bytes: 1_073_741_824,
  hwid_device_limit: 1,
  is_trial: true,
} as const

describe('витрина тарифов', () => {
  it('показывает цену, срок и лимиты платного тарифа', async () => {
    renderWithProviders(<Page />, { handlers: { '/api/plans': [paidPlan] } })

    const heading = await screen.findByRole('heading', { name: 'Месяц' })
    const card = heading.closest('[role="article"]')
    expect(card).not.toBeNull()
    const plan = within(card as HTMLElement)

    expect(plan.getByText('299 ₽')).toBeVisible()
    expect(plan.getByText('199 звёзд')).toBeVisible()
    expect(plan.getByText('на 30 дней')).toBeVisible()
    // Ноль означает безлимит, а не «нисколько трафика».
    expect(plan.getByText('∞')).toBeVisible()
    expect(plan.getByText('3')).toBeVisible()
  })

  it('помечает пробный тариф и не показывает у него цену', async () => {
    renderWithProviders(<Page />, { handlers: { '/api/plans': [trialPlan] } })

    const heading = await screen.findByRole('heading', { name: 'Пробный период' })
    const card = heading.closest('[role="article"]')
    expect(card).not.toBeNull()
    const plan = within(card as HTMLElement)

    expect(plan.getByText('Пробный')).toBeVisible()
    expect(plan.getByText('на 3 дня')).toBeVisible()
    expect(plan.queryByText(/₽|звёзд/)).not.toBeInTheDocument()
  })

  it('объясняет пустую витрину, а не показывает пустоту', async () => {
    renderWithProviders(<Page />, { handlers: { '/api/plans': [] } })
    expect(await screen.findByText('Тарифов пока нет')).toBeVisible()
  })

  it('показывает состояние загрузки', () => {
    renderWithProviders(<Page />, {
      handlers: { '/api/plans': () => new Promise(() => undefined) },
    })
    expect(screen.getByRole('status')).toHaveTextContent('Загрузка')
  })

  it('объясняет ошибку запроса и предлагает повторить', async () => {
    renderWithProviders(<Page />, {
      handlers: {
        '/api/plans': new Response(null, { status: 500 }),
      },
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('Что-то пошло не так')
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeVisible()
  })
})
