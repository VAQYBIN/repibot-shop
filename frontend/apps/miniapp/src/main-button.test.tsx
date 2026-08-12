import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useMainButton } from './main-button'

const offClick = vi.fn()
vi.mock('./telegram', () => ({
  hasMainButton: () => true,
  applyMainButton: vi.fn(),
  hideMainButton: vi.fn(),
  onMainButtonClick: (handler: () => void) => {
    void handler
    return offClick
  },
}))

function Screen() {
  useMainButton({ text: 'Купить', onClick: () => undefined })
  return <p>экран</p>
}

describe('useMainButton', () => {
  it('снимает обработчик при уходе с экрана', () => {
    /* Кнопка у Телеграма одна на всё приложение и переживает смену
       маршрута: неснятый обработчик сработает на следующем экране. */
    const view = render(<Screen />)

    view.unmount()

    expect(offClick).toHaveBeenCalled()
  })
})
