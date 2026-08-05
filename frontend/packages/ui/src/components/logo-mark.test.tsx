import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { LogoMark } from './logo-mark'

describe('LogoMark', () => {
  it('рисует спираль и отдельное ядро', () => {
    const { container } = render(<LogoMark />)

    expect(container.querySelector('path')).not.toBeNull()
    expect(container.querySelector('circle')).not.toBeNull()
  })

  it('красит спираль текущим цветом, а ядро — акцентом темы', () => {
    const { container } = render(<LogoMark />)

    expect(container.querySelector('path')?.getAttribute('stroke')).toBe('currentColor')
    expect(container.querySelector('circle')?.getAttribute('fill')).toBe('var(--rp-accent)')
  })

  it('упрощённая версия — один виток вместо полутора', () => {
    const { container } = render(<LogoMark variant="small" />)
    const path = container.querySelector('path')?.getAttribute('d') ?? ''

    expect((path.match(/A/g) ?? []).length).toBe(2)
  })

  it('полная версия — три дуги', () => {
    const { container } = render(<LogoMark />)
    const path = container.querySelector('path')?.getAttribute('d') ?? ''

    expect((path.match(/A/g) ?? []).length).toBe(3)
  })

  it('пропускает наружные атрибуты', () => {
    const { container } = render(<LogoMark height={24} aria-label="Re:Pibot" />)

    expect(container.querySelector('svg')?.getAttribute('height')).toBe('24')
    expect(container.querySelector('svg')?.getAttribute('aria-label')).toBe('Re:Pibot')
  })
})
