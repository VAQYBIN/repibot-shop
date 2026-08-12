import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchFromApi } from './server-api'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('серверный доступ к API', () => {
  it('ходит по внутреннему адресу, а не по относительному пути', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([{ slug: 'terms' }]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const data = await fetchFromApi<Array<{ slug: string }>>('/api/legal')

    expect(data).toEqual([{ slug: 'terms' }])
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('http://api:8000/api/legal')
  })

  it('берёт адрес из окружения, когда он задан', async () => {
    vi.stubEnv('INTERNAL_API_URL', 'http://127.0.0.1:9000')
    const fetchMock = vi.fn().mockResolvedValue(new Response('[]', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await fetchFromApi('/api/legal')

    expect(String(fetchMock.mock.calls[0]?.[0])).toBe('http://127.0.0.1:9000/api/legal')
  })

  it('возвращает null, когда API отвечает ошибкой', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 503 })))

    expect(await fetchFromApi('/api/plans')).toBeNull()
  })

  it('возвращает null, когда API недоступен', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))

    expect(await fetchFromApi('/api/plans')).toBeNull()
  })
})
