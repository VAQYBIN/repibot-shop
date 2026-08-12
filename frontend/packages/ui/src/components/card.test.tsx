import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Card } from './card'

describe('Card', () => {
  it('рендерит содержимое', () => {
    render(<Card>Подписка</Card>)

    expect(screen.getByText('Подписка')).toBeInTheDocument()
  })

  it('плоская: иерархию держат граница и фон, а не тень', () => {
    /* Тень остаётся только у того, что действительно висит над страницей:
       диалог, выпадающее меню, подсказка. Карточка лежит в потоке. */
    const { container } = render(<Card>Подписка</Card>)

    expect(container.firstElementChild?.className).not.toContain('shadow')
  })

  it('плотная: отступ 20px и средний радиус', () => {
    const { container } = render(<Card>Подписка</Card>)
    const classes = container.firstElementChild?.className.split(' ') ?? []

    expect(classes).toContain('p-5')
    expect(classes).toContain('rounded-md')
  })
})
