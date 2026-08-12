import { beforeEach, describe, expect, it, vi } from 'vitest'

import sitemap from './sitemap'

const fetchFromApi = vi.fn()

vi.mock('@/lib/server-api', () => ({ fetchFromApi: (path: string) => fetchFromApi(path) }))

beforeEach(() => fetchFromApi.mockReset())

describe('карта сайта', () => {
  it('перечисляет главную, тарифы и опубликованные документы', async () => {
    fetchFromApi.mockResolvedValue([
      { slug: 'terms', title: 'Условия', published_at: '2026-08-01T00:00:00Z' },
    ])

    const entries = await sitemap()

    expect(entries.map((entry) => entry.url)).toEqual([
      'http://localhost/',
      'http://localhost/plans',
      'http://localhost/legal/terms',
    ])
  })

  it('не содержит кабинета и админки', async () => {
    fetchFromApi.mockResolvedValue([])

    const urls = (await sitemap()).map((entry) => entry.url).join(' ')

    expect(urls).not.toContain('/account')
    expect(urls).not.toContain('/admin')
    expect(urls).not.toContain('/login')
  })

  it('отдаёт статические адреса, когда API недоступен', async () => {
    fetchFromApi.mockResolvedValue(null)

    expect(await sitemap()).toHaveLength(2)
  })
})
