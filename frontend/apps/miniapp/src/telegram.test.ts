import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  applyTelegramTheme,
  isInsideTelegram,
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
