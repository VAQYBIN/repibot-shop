import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Lockup } from './lockup'

describe('Lockup', () => {
  it('не тянет ни одного растра', () => {
    const { container } = render(<Lockup />)

    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('svg')).not.toBeNull()
  })

  it('на малых размерах берёт упрощённый знак', () => {
    const { container } = render(<Lockup size={24} />)
    const path = container.querySelector('path')?.getAttribute('d') ?? ''

    expect((path.match(/A/g) ?? []).length).toBe(2)
  })

  it('на обычных размерах берёт полный знак', () => {
    const { container } = render(<Lockup size={48} />)
    const path = container.querySelector('path')?.getAttribute('d') ?? ''

    expect((path.match(/A/g) ?? []).length).toBe(3)
  })

  it('показывает вордмарк с двоеточием', () => {
    const { getByText } = render(<Lockup />)

    expect(getByText(':')).toBeInTheDocument()
  })
})
