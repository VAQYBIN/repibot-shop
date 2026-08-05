import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithAuth } from '@/test/providers'
import { AuthGuard } from './auth-guard'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AuthGuard', () => {
  it('уводит на вход, когда обновление токена не удалось', async () => {
    const replace = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 401 })),
    )

    renderWithAuth(
      <AuthGuard router={{ replace }}>
        <p>кабинет</p>
      </AuthGuard>,
    )

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/login'))
    expect(screen.queryByText('кабинет')).not.toBeInTheDocument()
  })

  it('пускает внутрь, когда refresh-cookie ещё жива', async () => {
    const replace = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ access_token: 'jwt', expires_in: 900 })),
    )

    renderWithAuth(
      <AuthGuard router={{ replace }}>
        <p>кабинет</p>
      </AuthGuard>,
    )

    expect(await screen.findByText('кабинет')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })
})
