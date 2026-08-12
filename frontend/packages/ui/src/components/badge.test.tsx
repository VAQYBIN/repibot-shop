import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Badge } from './badge'

describe('Badge', () => {
  it('показывает слово, а не только цвет', () => {
    render(<Badge tone="success">Оплачен</Badge>)

    expect(screen.getByText('Оплачен')).toBeInTheDocument()
  })

  it('разные тона различаются классами', () => {
    const { rerender, container } = render(<Badge tone="danger">Отклонён</Badge>)
    const danger = container.firstElementChild?.className

    rerender(<Badge tone="neutral">Черновик</Badge>)

    expect(container.firstElementChild?.className).not.toBe(danger)
  })

  it('не объявляет себя скринридеру отдельным элементом', () => {
    /* Бейдж — оформление слова, стоящего рядом с предметом. Своей роли у него
       нет: лишняя роль заставила бы читать «статус» перед каждой строкой. */
    const { container } = render(<Badge tone="info">Ожидает</Badge>)

    expect(container.firstElementChild).not.toHaveAttribute('role')
  })
})
