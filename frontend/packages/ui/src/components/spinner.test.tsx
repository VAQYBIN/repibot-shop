import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Spinner } from './spinner'

describe('Spinner', () => {
  it('объявляет о себе как о состоянии', () => {
    render(<Spinner label="Загрузка подписки" />)

    expect(screen.getByRole('status', { name: 'Загрузка подписки' })).toBeInTheDocument()
  })

  it('вращается только обводка, ядро остаётся неподвижным', () => {
    /* Раздел 6 бренд-бука. Если класс уедет на весь знак, ядро начнёт
       обходить круг по орбите — это прямо запрещено. */
    const { container } = render(<Spinner />)

    expect(container.querySelector('path')).toHaveClass('rp-mark-spin')
    expect(container.querySelector('circle')).not.toHaveClass('rp-mark-spin')
  })

  it('ниже 32px берётся малая версия знака', () => {
    /* Раздел 4 бренд-бука запрещает решать слипание витков уменьшением
       полной версии. У малой другой viewBox — по нему и проверяем. */
    const { container } = render(<Spinner size={20} />)

    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 101 89')
  })

  it('от 32px берётся полная версия', () => {
    const { container } = render(<Spinner size={48} />)

    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 109 97')
  })
})
