import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Tooltip, TooltipProvider } from './tooltip'

describe('Tooltip', () => {
  it('называет кнопку и без наведения', () => {
    /* На телефоне наведения нет. Если подпись живёт только во всплывающем
       окошке, кнопка с одной иконкой остаётся безымянной навсегда. */
    render(
      <TooltipProvider>
        <Tooltip label="Отвязать устройство">
          <button type="button">✕</button>
        </Tooltip>
      </TooltipProvider>,
    )

    expect(screen.getByRole('button', { name: 'Отвязать устройство' })).toBeInTheDocument()
  })
})
