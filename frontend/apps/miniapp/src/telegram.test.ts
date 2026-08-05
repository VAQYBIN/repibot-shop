import { afterEach, describe, expect, it, vi } from 'vitest'

import { applyTelegramTheme, isInsideTelegram, readInitData } from './telegram'

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
