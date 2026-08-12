import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LandingHero } from './hero'

vi.mock('@repibot/core', () => ({ translate: (_: string, key: string) => key }))

describe('первый экран лендинга', () => {
  it('зовёт на пробный период, когда триальный тариф есть', () => {
    render(<LandingHero hasTrial={true} />)

    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'landing.hero.cta_trial' })).toHaveAttribute(
      'href',
      '/register',
    )
  })

  it('не обещает пробный период, когда его выключили', () => {
    render(<LandingHero hasTrial={false} />)

    expect(screen.queryByRole('link', { name: 'landing.hero.cta_trial' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'landing.hero.cta_plans' })).toHaveAttribute(
      'href',
      '/plans',
    )
  })
})
