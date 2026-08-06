import { createTokenStore } from '@repibot/core'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { exchangeInitData, useAuthState } from './auth'

afterEach(() => {
  vi.unstubAllGlobals()
  useAuthState.setState({ state: 'checking' })
})

describe('вход в MiniApp', () => {
  it('обменивает initData на токен', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ access_token: 'token', expires_in: 900 })),
    )
    const store = createTokenStore()

    const ok = await exchangeInitData({ baseUrl: '', store }, 'auth_date=1&hash=abc')

    expect(ok).toBe(true)
    expect(store.get()).toBe('token')
  })

  it('сообщает о неудаче, а не молчит', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'invalid_credentials' } }, { status: 401 })),
    )
    const store = createTokenStore()

    expect(await exchangeInitData({ baseUrl: '', store }, 'испорчено')).toBe(false)
    expect(store.get()).toBeNull()
  })

  it('различает открытие вне Telegram', async () => {
    // Без initData обмен не пробуется вовсе: сообщение «войдите через Telegram»
    // полезнее, чем сетевая ошибка.
    expect(await exchangeInitData({ baseUrl: '', store: createTokenStore() }, '')).toBe(false)
  })
})

describe('состояние входа', () => {
  it('вне Telegram переходит в outside и не трогает сеть', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await useAuthState.getState().signIn({ baseUrl: '', store: createTokenStore() })

    expect(useAuthState.getState().state).toBe('outside')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('после удачного обмена готов к работе', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'auth_date=1&hash=abc' } })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ access_token: 'token', expires_in: 900 })),
    )

    await useAuthState.getState().signIn({ baseUrl: '', store: createTokenStore() })

    expect(useAuthState.getState().state).toBe('ready')
  })

  it('неудачный обмен отличается от открытия вне Telegram', async () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'auth_date=1&hash=abc' } })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'token_invalid' } }, { status: 401 })),
    )

    await useAuthState.getState().signIn({ baseUrl: '', store: createTokenStore() })

    expect(useAuthState.getState().state).toBe('failed')
  })
})
