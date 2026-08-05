import { afterEach, describe, expect, it, vi } from 'vitest'

import { createAuthClient } from '../auth/client'
import { createTokenStore } from '../auth/store'
import { createApiClient } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('клиент API', () => {
  it('добавляет заголовок авторизации, когда токен есть', async () => {
    // Параметр объявлен явно: без него тип calls — пустой кортеж, и обращение
    // к calls[0][0] не проходит проверку типов.
    const fetchMock = vi.fn(async (_request: Request) => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const client = createApiClient('https://example.org', () => 'token-123')
    await client.GET('/health')

    const request = fetchMock.mock.calls[0]?.[0]
    expect(request).toBeDefined()
    expect(request?.headers.get('authorization')).toBe('Bearer token-123')
  })

  it('не добавляет заголовок, когда токена нет', async () => {
    // Параметр объявлен явно: без него тип calls — пустой кортеж, и обращение
    // к calls[0][0] не проходит проверку типов.
    const fetchMock = vi.fn(async (_request: Request) => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const client = createApiClient('https://example.org', () => null)
    await client.GET('/health')

    const request = fetchMock.mock.calls[0]?.[0]
    expect(request).toBeDefined()
    expect(request?.headers.get('authorization')).toBeNull()
  })
})

describe('createAuthClient', () => {
  it('обновляет токен один раз на несколько параллельных 401', async () => {
    let refreshCalls = 0
    const fetchMock = vi.fn(async (request: Request) => {
      if (request.url.endsWith('/api/auth/refresh')) {
        refreshCalls += 1
        return Response.json({ access_token: 'fresh', expires_in: 900 })
      }
      const auth = request.headers.get('Authorization')
      if (auth !== 'Bearer fresh') {
        return Response.json({ error: { code: 'unauthorized' } }, { status: 401 })
      }
      return Response.json({ id: 1 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const store = createTokenStore()
    store.set('stale')
    const client = createAuthClient({ baseUrl: 'https://api.test', store })

    const results = await Promise.all([
      client.api.GET('/api/me'),
      client.api.GET('/api/me'),
      client.api.GET('/api/me'),
    ])

    // Один refresh на три запроса: иначе три вкладки ротируют токен друг под
    // другом и выбивают сессию.
    expect(refreshCalls).toBe(1)
    expect(results.every((result) => result.data !== undefined)).toBe(true)
  })

  it('сообщает о выходе, когда обновление не удалось', async () => {
    const onSignedOut = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'unauthorized' } }, { status: 401 })),
    )
    const store = createTokenStore()
    store.set('stale')
    const client = createAuthClient({ baseUrl: 'https://api.test', store, onSignedOut })

    await client.api.GET('/api/me')

    expect(onSignedOut).toHaveBeenCalledOnce()
    expect(store.get()).toBeNull()
  })

  it('не пытается обновиться в ответ на 401 самого обновления', async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({ error: { code: 'unauthorized' } }, { status: 401 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const client = createAuthClient({ baseUrl: 'https://api.test', store: createTokenStore() })

    await client.refresh()

    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
