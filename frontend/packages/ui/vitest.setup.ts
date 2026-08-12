import '@testing-library/jest-dom/vitest'

// jsdom не реализует PointerEvent, а Radix (DropdownMenu, Tooltip и другие)
// слушает именно его при открытии по клику. Без полифила клик по триггеру
// в тестах остаётся без ответа — не потому что компонент сломан, а потому
// что событие, которого он ждёт, не существует в этой среде.
if (typeof window.PointerEvent === 'undefined') {
  class PointerEvent extends MouseEvent {
    public readonly pointerId: number
    public readonly pointerType: string

    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params)
      this.pointerId = params.pointerId ?? 0
      this.pointerType = params.pointerType ?? 'mouse'
    }
  }

  // @ts-expect-error — полифил только для тестовой среды, не для рантайма.
  window.PointerEvent = PointerEvent
}
