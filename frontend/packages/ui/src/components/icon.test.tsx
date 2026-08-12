import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Icon } from './icon'

/* Своя геометрия вместо настоящей иконки: тест про обёртку, а не про
   содержимое пакета, и от смены набора иконок он зависеть не должен. */
const SQUARE = [['path', { d: 'M4 4h16v16H4z' }]] as const

describe('Icon', () => {
  it('без названия иконка декоративна и от скринридера скрыта', () => {
    const { container } = render(<Icon icon={SQUARE} />)
    const svg = container.querySelector('svg')

    expect(svg).toHaveAttribute('aria-hidden', 'true')
    expect(svg).not.toHaveAttribute('role', 'img')
  })

  it('с названием иконка становится картинкой с подписью', () => {
    render(<Icon icon={SQUARE} title="Устройства" />)

    expect(screen.getByRole('img', { name: 'Устройства' })).toBeInTheDocument()
  })

  it('размер по умолчанию — 20', () => {
    const { container } = render(<Icon icon={SQUARE} />)

    expect(container.querySelector('svg')).toHaveAttribute('width', '20')
  })

  it('размер задаётся явно', () => {
    const { container } = render(<Icon icon={SQUARE} size={24} />)

    expect(container.querySelector('svg')).toHaveAttribute('width', '24')
  })
})
