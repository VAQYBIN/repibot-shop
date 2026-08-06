import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { FormField } from './form-field'
import { Input } from './input'

describe('FormField', () => {
  it('связывает подпись с полем', () => {
    render(
      <FormField label="Почта" htmlFor="email">
        <Input id="email" />
      </FormField>,
    )

    expect(screen.getByLabelText('Почта')).toHaveAttribute('id', 'email')
  })

  it('ошибку помечает role="alert" и привязывает к полю', () => {
    render(
      <FormField label="Почта" htmlFor="email" error="Некорректный адрес">
        <Input id="email" />
      </FormField>,
    )

    const field = screen.getByLabelText('Почта')
    const alert = screen.getByRole('alert')

    expect(alert).toHaveTextContent('Некорректный адрес')
    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(field.getAttribute('aria-describedby')).toBe(alert.id)
  })

  it('подсказку тоже привязывает к полю, но без alert', () => {
    render(
      <FormField label="Пароль" htmlFor="password" hint="Не меньше десяти символов">
        <Input id="password" />
      </FormField>,
    )

    const field = screen.getByLabelText('Пароль')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(field.getAttribute('aria-describedby')).toBe('password-hint')
    expect(field).not.toHaveAttribute('aria-invalid')
  })

  it('перечисляет подсказку и ошибку вместе', () => {
    render(
      <FormField label="Пароль" htmlFor="password" hint="Подсказка" error="Ошибка">
        <Input id="password" />
      </FormField>,
    )

    expect(screen.getByLabelText('Пароль').getAttribute('aria-describedby')).toBe(
      'password-hint password-error',
    )
  })

  it('без ошибки и подсказки не навешивает лишних атрибутов', () => {
    render(
      <FormField label="Почта" htmlFor="email">
        <Input id="email" />
      </FormField>,
    )

    expect(screen.getByLabelText('Почта')).not.toHaveAttribute('aria-describedby')
  })
})
