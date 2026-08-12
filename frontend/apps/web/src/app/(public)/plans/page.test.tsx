import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

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

/**
 * Соседний экран для проверки ухода с витрины.
 *
 * Настоящей главной здесь больше нет: она стала серверным компонентом с
 * запросом тарифов, а такой не отрисовать клиентским рендером. Роль у неё в
 * этом тесте была ровно одна — «любой другой экран», и заглушка исполняет её
 * без сети.
 */
function OtherScreen() {
  return <h1>Другой экран</h1>
}

function RouteSequence() {
  const [route, setRoute] = useState<'plans' | 'other'>('plans')
  return route === 'plans' ? (
    <>
      <Page />
      <button type="button" onClick={() => setRoute('other')}>
        На главную
      </button>
    </>
  ) : (
    <OtherScreen />
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.documentElement.lang = 'ru'
  document.documentElement.dataset.theme = 'light'
})

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
    expect(plan.getByText('Трафик')).toHaveClass('text-text-secondary')
    expect(plan.getByText('Устройства')).toHaveClass('text-text-secondary')
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
        '/api/plans': { status: 500, body: null },
      },
    })
    expect(await screen.findByRole('alert')).toHaveTextContent('Что-то пошло не так')
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeVisible()
  })

  it('применяет тёмную тему из системных настроек', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: true,
        media: '(prefers-color-scheme: dark)',
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    )
    document.documentElement.dataset.theme = 'light'

    renderWithProviders(<Page />, { handlers: { '/api/plans': [] } })

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
  })

  it('синхронизирует язык документа с языком витрины', async () => {
    vi.stubGlobal('navigator', {
      ...navigator,
      languages: ['en-US', 'en'],
      language: 'en-US',
    })
    document.documentElement.lang = 'ru'

    renderWithProviders(<Page />, { handlers: { '/api/plans': [] } })

    expect(await screen.findByRole('heading', { name: 'Plans' })).toBeVisible()
    await waitFor(() => expect(document.documentElement.lang).toBe('en'))
  })

  it('возвращает русский язык документа после ухода с английской витрины', async () => {
    vi.stubGlobal('navigator', {
      ...navigator,
      languages: ['en-US', 'en'],
      language: 'en-US',
    })
    document.documentElement.lang = 'ru'

    renderWithProviders(<RouteSequence />, { handlers: { '/api/plans': [] } })
    expect(await screen.findByRole('heading', { name: 'Plans' })).toBeVisible()
    await waitFor(() => expect(document.documentElement.lang).toBe('en'))

    fireEvent.click(screen.getByRole('button', { name: 'На главную' }))

    expect(await screen.findByText('Другой экран')).toBeVisible()
    expect(document.documentElement.lang).toBe('ru')
  })
})
