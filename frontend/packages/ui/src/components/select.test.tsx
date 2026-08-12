import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Select } from './select'

function Languages(props: { onChange?: (value: string) => void }) {
  return (
    <Select
      aria-label="Язык"
      defaultValue="ru"
      onChange={(event) => props.onChange?.(event.target.value)}
    >
      <option value="ru">Русский</option>
      <option value="en">English</option>
    </Select>
  )
}

describe('Select', () => {
  it('остаётся нативным списком', () => {
    render(<Languages />)

    expect(screen.getByRole('combobox', { name: 'Язык' })).toBeInTheDocument()
  })

  it('сообщает о выборе', async () => {
    const onChange = vi.fn()
    render(<Languages onChange={onChange} />)

    await userEvent.selectOptions(screen.getByRole('combobox'), 'en')

    expect(onChange).toHaveBeenCalledWith('en')
  })

  it('признак ошибки объявляется скринридеру, а не только краской', () => {
    render(
      <Select aria-label="Язык" invalid>
        <option value="ru">Русский</option>
      </Select>,
    )

    expect(screen.getByRole('combobox')).toHaveAttribute('aria-invalid', 'true')
  })
})
