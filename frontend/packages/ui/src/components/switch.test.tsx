import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Switch } from './switch'

describe('Switch', () => {
  it('доступен как переключатель с подписью', () => {
    render(<Switch checked={false} onCheckedChange={vi.fn()} label="Тёмная тема" />)

    expect(screen.getByRole('switch', { name: 'Тёмная тема' })).toBeInTheDocument()
  })

  it('сообщает состояние через aria-checked', () => {
    const { rerender } = render(
      <Switch checked={false} onCheckedChange={vi.fn()} label="Тёмная тема" />,
    )

    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')

    rerender(<Switch checked onCheckedChange={vi.fn()} label="Тёмная тема" />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  it('отдаёт новое значение наверх', () => {
    const onCheckedChange = vi.fn()
    render(<Switch checked={false} onCheckedChange={onCheckedChange} label="Тёмная тема" />)

    fireEvent.click(screen.getByRole('switch'))

    expect(onCheckedChange).toHaveBeenCalledWith(true)
  })

  // Проверяем именно атрибут: jsdom доставляет клик и отключённому полю,
  // поэтому отсутствие вызова здесь ничего бы не доказывало.
  it('отключённый переключатель недоступен', () => {
    render(<Switch checked={false} onCheckedChange={vi.fn()} label="Тёмная тема" disabled />)

    expect(screen.getByRole('switch')).toBeDisabled()
  })
})
