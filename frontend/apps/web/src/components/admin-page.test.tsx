import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AdminPage } from './admin-page'

describe('AdminPage', () => {
  it('заголовок — первого уровня', () => {
    /* На нём держится сквозной обход экранов: страница без h1 означает
       разметку, которая не собралась, а не страницу без названия. */
    render(<AdminPage title="Пользователи">содержимое</AdminPage>)

    expect(screen.getByRole('heading', { level: 1, name: 'Пользователи' })).toBeInTheDocument()
  })

  it('описание необязательно', () => {
    const { container } = render(<AdminPage title="Ноды">содержимое</AdminPage>)

    expect(container.querySelector('p')).toBeNull()
  })

  it('показывает описание и действия, когда они есть', () => {
    render(
      <AdminPage
        title="Рассылки"
        description="Кампании по сегментам"
        actions={<button type="button">Создать</button>}
      >
        содержимое
      </AdminPage>,
    )

    expect(screen.getByText('Кампании по сегментам')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Создать' })).toBeInTheDocument()
  })

  it('показывает содержимое страницы', () => {
    render(<AdminPage title="Сводка">содержимое</AdminPage>)

    expect(screen.getByText('содержимое')).toBeInTheDocument()
  })
})
