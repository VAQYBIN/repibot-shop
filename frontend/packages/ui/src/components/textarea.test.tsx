import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Textarea } from './textarea'

describe('Textarea', () => {
  it('принимает текст', async () => {
    render(<Textarea aria-label="Сообщение" />)

    await userEvent.type(screen.getByRole('textbox', { name: 'Сообщение' }), 'Не открывается')

    expect(screen.getByRole('textbox')).toHaveValue('Не открывается')
  })

  it('признак ошибки объявляется скринридеру', () => {
    render(<Textarea aria-label="Сообщение" invalid />)

    expect(screen.getByRole('textbox')).toHaveAttribute('aria-invalid', 'true')
  })

  it('высота задаётся снаружи и не сбрасывается', () => {
    render(<Textarea aria-label="Сообщение" className="min-h-40" />)

    expect(screen.getByRole('textbox').className).toContain('min-h-40')
  })
})
