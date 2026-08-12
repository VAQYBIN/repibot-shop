import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './dropdown-menu'

function Actions({ onBan }: { onBan?: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger>Действия</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onSelect={() => undefined}>Заглушить</DropdownMenuItem>
        <DropdownMenuItem tone="danger" onSelect={() => onBan?.()}>
          Заблокировать
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

describe('DropdownMenu', () => {
  it('закрыт до нажатия', () => {
    render(<Actions />)

    expect(screen.queryByRole('menuitem', { name: 'Заглушить' })).toBeNull()
  })

  it('открывается и выполняет выбранное', async () => {
    const onBan = vi.fn()
    render(<Actions onBan={onBan} />)

    await userEvent.click(screen.getByRole('button', { name: 'Действия' }))
    await userEvent.click(screen.getByRole('menuitem', { name: 'Заблокировать' }))

    expect(onBan).toHaveBeenCalledOnce()
  })

  it('опасное действие отличается от остальных', async () => {
    render(<Actions />)
    await userEvent.click(screen.getByRole('button', { name: 'Действия' }))

    expect(screen.getByRole('menuitem', { name: 'Заблокировать' }).className).toContain('danger')
    expect(screen.getByRole('menuitem', { name: 'Заглушить' }).className).not.toContain('danger')
  })
})
