// @vitest-environment jsdom
// Окружение переопределено на jsdom: в node-окружении localStorage и
// sessionStorage просто не существуют, и проверка «токена там нет» ничего бы не
// проверяла.

import { describe, expect, it, vi } from 'vitest'

import { createTokenStore } from './store'

describe('createTokenStore', () => {
  it('хранит токен только в памяти', () => {
    const store = createTokenStore()

    store.set('token')

    expect(store.get()).toBe('token')
    // Ни localStorage, ни sessionStorage: в веб-версии Telegram чужой контекст,
    // а XSS достаёт оттуда токен одной строкой.
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('уведомляет подписчиков о смене', () => {
    const store = createTokenStore()
    const listener = vi.fn()
    store.subscribe(listener)

    store.set('token')
    store.set(null)

    expect(listener).toHaveBeenCalledTimes(2)
  })
})
