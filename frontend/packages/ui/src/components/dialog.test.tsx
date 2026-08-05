import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { Button } from './button'
import { Dialog } from './dialog'

function Confirm({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Отозвать сессию?" description="Устройство выйдет">
      <Button variant="secondary" onClick={onClose}>
        Отмена
      </Button>
      <Button>Отозвать</Button>
    </Dialog>
  )
}

describe('Dialog', () => {
  it('закрытое окно ничего не рисует', () => {
    render(<Confirm open={false} onClose={vi.fn()} />)

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('объявляет себя модальным и подписывается заголовком', () => {
    render(<Confirm open onClose={vi.fn()} />)

    const dialog = screen.getByRole('dialog', { name: 'Отозвать сессию?' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleDescription('Устройство выйдет')
  })

  it('отдаёт фокус первой кнопке при открытии', () => {
    render(<Confirm open onClose={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Отмена' })).toHaveFocus()
  })

  it('Escape закрывает окно', () => {
    const onClose = vi.fn()
    render(<Confirm open onClose={onClose} />)

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('Tab с последней кнопки возвращает фокус на первую', () => {
    render(<Confirm open onClose={vi.fn()} />)

    const revoke = screen.getByRole('button', { name: 'Отозвать' })
    revoke.focus()
    fireEvent.keyDown(document, { key: 'Tab' })

    expect(screen.getByRole('button', { name: 'Отмена' })).toHaveFocus()
  })

  it('Shift+Tab с первой кнопки уводит на последнюю', () => {
    render(<Confirm open onClose={vi.fn()} />)

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })

    expect(screen.getByRole('button', { name: 'Отозвать' })).toHaveFocus()
  })

  it('возвращает фокус вызвавшему элементу после закрытия', () => {
    function Host() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Открыть
          </button>
          <Confirm open={open} onClose={() => setOpen(false)} />
        </>
      )
    }

    render(<Host />)
    const opener = screen.getByRole('button', { name: 'Открыть' })
    opener.focus()
    fireEvent.click(opener)
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(opener).toHaveFocus()
  })
})
