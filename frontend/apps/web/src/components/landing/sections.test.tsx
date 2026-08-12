import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LandingFaq } from './faq'
import { LandingReasons } from './reasons'
import { LandingSteps } from './steps'

vi.mock('@repibot/core', () => ({ translate: (_: string, key: string) => key }))

describe('разделы лендинга', () => {
  it('показывает ровно четыре довода', () => {
    render(<LandingReasons />)

    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(4)
    expect(screen.getByText('landing.reason.trial.text')).toBeInTheDocument()
  })

  it('показывает три шага по порядку', () => {
    render(<LandingSteps />)

    const headings = screen.getAllByRole('heading', { level: 3 }).map((node) => node.textContent)
    expect(headings).toEqual([
      'landing.step.account.title',
      'landing.step.plan.title',
      'landing.step.connect.title',
    ])
  })

  it('показывает шесть вопросов и держит ответы свёрнутыми', () => {
    render(<LandingFaq />)

    const questions = screen.getAllByRole('group')
    expect(questions).toHaveLength(6)
    for (const question of questions) {
      expect(question).not.toHaveAttribute('open')
    }
  })
})
