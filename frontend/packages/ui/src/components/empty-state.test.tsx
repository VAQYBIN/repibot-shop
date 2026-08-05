import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Button } from './button'
import { EmptyState } from './empty-state'

describe('EmptyState', () => {
  it('показывает заголовок и описание', () => {
    render(<EmptyState title="Сессий нет" description="Вы вошли только здесь" />)

    expect(screen.getByText('Сессий нет')).toBeInTheDocument()
    expect(screen.getByText('Вы вошли только здесь')).toBeInTheDocument()
  })

  it('показывает действие, когда оно передано', () => {
    render(<EmptyState title="Сессий нет" action={<Button>Обновить</Button>} />)

    expect(screen.getByRole('button', { name: 'Обновить' })).toBeInTheDocument()
  })

  it('без действия не оставляет пустой кнопки', () => {
    render(<EmptyState title="Сессий нет" />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
