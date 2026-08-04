import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Button } from './button'

describe('Button', () => {
  it('рендерит содержимое', () => {
    render(<Button>Купить</Button>)

    expect(screen.getByRole('button', { name: 'Купить' })).toBeInTheDocument()
  })

  it('основной вариант заливается акцентом', () => {
    render(<Button variant="primary">Купить</Button>)

    expect(screen.getByRole('button')).toHaveClass('bg-accent')
  })

  it('второстепенный вариант — без заливки, с границей', () => {
    render(<Button variant="secondary">Отмена</Button>)

    const button = screen.getByRole('button')
    expect(button).not.toHaveClass('bg-accent')
    expect(button.className).toContain('border')
  })

  it('мелкий размер использует тёмный текст на зелёном', () => {
    /* Белый на Jade даёт 3.4:1 и проходит только от 18-19 px.
       Для мелкой кнопки бренд-бук требует #08150F. */
    render(
      <Button variant="primary" size="sm">
        Ок
      </Button>,
    )

    expect(screen.getByRole('button').className).toContain('text-[#08150F]')
  })

  it('отключённая кнопка недоступна для нажатия', () => {
    render(<Button disabled>Купить</Button>)

    expect(screen.getByRole('button')).toBeDisabled()
  })
})
