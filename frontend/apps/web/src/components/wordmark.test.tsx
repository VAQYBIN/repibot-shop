import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Wordmark } from './wordmark'

describe('Wordmark', () => {
  it('пишется строчными', () => {
    render(<Wordmark />)

    expect(screen.getByText(/re/).textContent).toBe('re')
  })

  it('двоеточие вынесено отдельным элементом в цвете акцента', () => {
    /* Двоеточие — часть марки, а не пунктуация: раздел 5 бренд-бука
       запрещает убирать его или красить в основной цвет. */
    render(<Wordmark />)

    const colon = screen.getByText(':')
    expect(colon).toBeInTheDocument()
    expect(colon.className).toContain('text-accent')
  })

  it('целиком читается как re:pibot', () => {
    const { container } = render(<Wordmark />)

    expect(container.textContent).toBe('re:pibot')
  })
})
