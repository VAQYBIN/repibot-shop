import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { useLegalDocuments } from './hooks'

const get = vi.fn()

vi.mock('../auth/hooks', () => ({
  useAuthClient: () => ({ api: { GET: get } }),
}))

function wrapper({ children }: { children: ReactNode }) {
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={queries}>{children}</QueryClientProvider>
}

describe('useLegalDocuments', () => {
  it('запрашивает документы для выбранного языка', async () => {
    get.mockResolvedValue({
      data: [{ slug: 'terms', title: 'Условия', published_at: '2026-08-01T00:00:00Z' }],
      error: undefined,
    })

    const { result } = renderHook(() => useLegalDocuments('en'), { wrapper })

    await waitFor(() => expect(result.current.data).toHaveLength(1))
    expect(get).toHaveBeenCalledWith('/api/legal', { params: { query: { locale: 'en' } } })
  })

  it('пустой список — обычный ответ, а не ошибка', async () => {
    get.mockResolvedValue({ data: [], error: undefined })

    const { result } = renderHook(() => useLegalDocuments('ru'), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })
})
