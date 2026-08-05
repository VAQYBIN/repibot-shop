import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PasswordInput } from './password-input'

describe('PasswordInput', () => {
  it('по умолчанию скрывает пароль', () => {
    const { container } = render(<PasswordInput id="password" />)

    expect(container.querySelector('input')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false')
  })

  it('кнопка показа переключает тип поля и своё состояние', () => {
    const { container } = render(<PasswordInput id="password" />)

    fireEvent.click(screen.getByRole('button', { name: 'Показать пароль' }))

    expect(container.querySelector('input')).toHaveAttribute('type', 'text')
    const button = screen.getByRole('button', { name: 'Скрыть пароль' })
    expect(button).toHaveAttribute('aria-pressed', 'true')
  })

  it('берёт подписи кнопки из приложения', () => {
    render(<PasswordInput id="password" showLabel="Show password" hideLabel="Hide password" />)

    expect(screen.getByRole('button', { name: 'Show password' })).toBeInTheDocument()
  })

  it('пропускает aria-атрибуты внутрь поля', () => {
    const { container } = render(<PasswordInput id="password" aria-describedby="password-error" />)

    expect(container.querySelector('input')).toHaveAttribute('aria-describedby', 'password-error')
  })

  it('кнопка не отправляет форму', () => {
    render(<PasswordInput id="password" />)

    expect(screen.getByRole('button')).toHaveAttribute('type', 'button')
  })
})
