import { afterEach, describe, expect, it, vi } from 'vitest'

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
