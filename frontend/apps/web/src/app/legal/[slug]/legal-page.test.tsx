import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import LegalPage from './page'

const fetchFromApi = vi.fn()
const notFound = vi.fn(() => {
  throw new Error('NEXT_NOT_FOUND')
})

vi.mock('@/lib/server-api', () => ({ fetchFromApi: (path: string) => fetchFromApi(path) }))
vi.mock('next/navigation', () => ({ notFound: () => notFound() }))
vi.mock('@repibot/core', () => ({ translate: () => 'Действует с {date}' }))

beforeEach(() => {
  fetchFromApi.mockReset()
  notFound.mockClear()
})

describe('страница юридического документа', () => {
  it('показывает заголовок и содержимое документа', async () => {
    fetchFromApi.mockResolvedValue({
      slug: 'terms',
      title: 'Пользовательское соглашение',
      html: '<h2>Общие положения</h2>\n<p>Текст.</p>',
      locale: 'ru',
      version: 3,
      published_at: '2026-08-01T00:00:00Z',
    })

    render(await LegalPage({ params: Promise.resolve({ slug: 'terms' }) }))

    expect(
      screen.getByRole('heading', { level: 1, name: 'Пользовательское соглашение' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Общие положения' })).toBeInTheDocument()
  })

  it('отдаёт 404, когда документа нет', async () => {
    fetchFromApi.mockResolvedValue(null)

    await expect(LegalPage({ params: Promise.resolve({ slug: 'nothing' }) })).rejects.toThrow(
      'NEXT_NOT_FOUND',
    )
    expect(notFound).toHaveBeenCalled()
  })
})
