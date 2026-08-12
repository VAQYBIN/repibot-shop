import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  applyMainButton,
  applyTelegramTheme,
  haptic,
  hasMainButton,
  isInsideTelegram,
  onMainButtonClick,
  readInitData,
  watchTelegramActivity,
} from './telegram'

afterEach(() => {
  vi.unstubAllGlobals()
  document.documentElement.removeAttribute('data-theme')
})

function stubTelegram(webApp: Record<string, unknown>): void {
  vi.stubGlobal('Telegram', { WebApp: webApp })
}

describe('интеграция с Telegram', () => {
  it('читает initData, когда приложение открыто внутри Telegram', () => {
    stubTelegram({ initData: 'query_id=AAA&user=%7B%22id%22%3A1%7D', ready: vi.fn() })

    expect(readInitData()).toBe('query_id=AAA&user=%7B%22id%22%3A1%7D')
  })

  it('возвращает null в обычном браузере', () => {
    expect(readInitData()).toBeNull()
  })

  it('пустую строку initData не выдаёт за валидную', () => {
    /* Telegram отдаёт пустую строку, когда приложение открыто не из бота —
       принять её за подтверждение личности нельзя. */
    stubTelegram({ initData: '', ready: vi.fn() })

    expect(readInitData()).toBeNull()
  })

  it('определяет запуск внутри Telegram', () => {
    stubTelegram({ initData: 'x', ready: vi.fn() })
    expect(isInsideTelegram()).toBe(true)
  })

  it('переносит тёмную тему Telegram на корневой элемент', () => {
    stubTelegram({ initData: 'x', colorScheme: 'dark', ready: vi.fn() })

    applyTelegramTheme()

    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('вне Telegram тему не трогает', () => {
    applyTelegramTheme()

    expect(document.documentElement.dataset.theme).toBeUndefined()
  })
})

/** Обработчики Telegram по имени события: тест вызывает их вместо клиента. */
function stubTelegramEvents(): Map<string, () => void> {
  const handlers = new Map<string, () => void>()
  stubTelegram({
    initData: 'x',
    ready: vi.fn(),
    onEvent: (event: string, handler: () => void) => handlers.set(event, handler),
    offEvent: (event: string) => handlers.delete(event),
  })
  return handlers
}

describe('возврат в Mini App', () => {
  it('сообщает о сворачивании и разворачивании событиями Telegram', () => {
    const handlers = stubTelegramEvents()
    const seen: boolean[] = []

    watchTelegramActivity((active) => seen.push(active))
    handlers.get('deactivated')?.()
    handlers.get('activated')?.()

    expect(seen).toEqual([false, true])
  })

  it('отписывается от событий Telegram', () => {
    const handlers = stubTelegramEvents()

    watchTelegramActivity(vi.fn())()

    expect([...handlers.keys()]).toEqual([])
  })

  it('вне Telegram слушает видимость документа', () => {
    /* Старые клиенты и обычный браузер о своих событиях не знают, и остаётся
       единственный сигнал, который у них есть. */
    const seen: boolean[] = []

    const stop = watchTelegramActivity((active) => seen.push(active))
    document.dispatchEvent(new Event('visibilitychange'))
    stop()
    document.dispatchEvent(new Event('visibilitychange'))

    expect(seen).toEqual([true])
  })
})

/** Главная кнопка и вибрация есть не в каждом клиенте: старые версии Telegram
    их не поддерживают, и признак поддержки экран обязан проверять сам. */
function stubMainButton(withMainButton: boolean) {
  const main = {
    setText: vi.fn(),
    show: vi.fn(),
    hide: vi.fn(),
    enable: vi.fn(),
    disable: vi.fn(),
    showProgress: vi.fn(),
    hideProgress: vi.fn(),
    onClick: vi.fn(),
    offClick: vi.fn(),
  }
  const notificationOccurred = vi.fn()
  const impactOccurred = vi.fn()
  stubTelegram({
    ...(withMainButton ? { MainButton: main } : {}),
    HapticFeedback: { notificationOccurred, impactOccurred },
  })
  return { main, notificationOccurred, impactOccurred }
}

describe('главная кнопка Telegram', () => {
  it('в клиенте без кнопки признак отрицательный', () => {
    /* Ради этого признака всё и написано: экран обязан уметь показать
       обычную кнопку, иначе покупка в старом клиенте невозможна. */
    stubMainButton(false)

    expect(hasMainButton()).toBe(false)
  })

  it('применяет состояние целиком', () => {
    const { main } = stubMainButton(true)

    applyMainButton({ text: 'Купить', visible: true, loading: false, disabled: false })

    expect(main.setText).toHaveBeenCalledWith('Купить')
    expect(main.show).toHaveBeenCalled()
    expect(main.enable).toHaveBeenCalled()
  })

  it('снятие обработчика возвращается вызывающему', () => {
    const { main } = stubMainButton(true)
    const handler = vi.fn()

    const off = onMainButtonClick(handler)
    off()

    expect(main.onClick).toHaveBeenCalledWith(handler)
    expect(main.offClick).toHaveBeenCalledWith(handler)
  })

  it('вне Telegram ничего не падает', () => {
    expect(() =>
      applyMainButton({ text: 'Купить', visible: true, loading: false, disabled: false }),
    ).not.toThrow()
    expect(() => haptic('success')).not.toThrow()
  })
})

describe('вибрация Telegram', () => {
  it('успех и отказ переводятся в уведомления, обычное нажатие — в лёгкий удар', () => {
    const { notificationOccurred, impactOccurred } = stubMainButton(true)

    haptic('success')
    haptic('error')
    haptic('tap')

    expect(notificationOccurred).toHaveBeenCalledWith('success')
    expect(notificationOccurred).toHaveBeenCalledWith('error')
    expect(impactOccurred).toHaveBeenCalledWith('light')
  })
})
