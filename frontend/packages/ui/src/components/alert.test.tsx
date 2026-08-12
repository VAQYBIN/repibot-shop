import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Alert } from './alert'

describe('Alert', () => {
  it('об отказе объявляет немедленно', () => {
    render(<Alert tone="error">Карта отклонена</Alert>)

    expect(screen.getByRole('alert')).toHaveTextContent('Карта отклонена')
  })

  it('об успехе объявляет в свою очередь', () => {
    /* role=status не перебивает человека на полуслове. Для успеха это верно,
       для отказа — нет: там ждать нечего. */
    render(<Alert tone="success">Оплачено</Alert>)

    expect(screen.getByRole('status')).toHaveTextContent('Оплачено')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('заголовок необязателен и не создаёт пустой строки', () => {
    const { container } = render(<Alert tone="info">Продление через три дня</Alert>)

    expect(container.querySelector('p.font-medium')).toBeNull()
  })

  it('с заголовком показывает и его, и текст', () => {
    render(
      <Alert tone="warning" title="Подписка кончается">
        Осталось два дня
      </Alert>,
    )

    expect(screen.getByText('Подписка кончается')).toBeInTheDocument()
    expect(screen.getByText('Осталось два дня')).toBeInTheDocument()
  })
})
