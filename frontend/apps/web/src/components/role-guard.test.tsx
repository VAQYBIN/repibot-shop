import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithAuth } from '@/test/providers'
import { RoleGuard } from './role-guard'

function stubApi(role: string) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      if (request.url.endsWith('/api/auth/refresh')) {
        return Response.json({ access_token: 'jwt', expires_in: 900 })
      }
      return Response.json({ id: 1, role })
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RoleGuard', () => {
  it('уводит в кабинет, когда роли не хватает', async () => {
    const replace = vi.fn()
    stubApi('user')

    renderWithAuth(
      <RoleGuard router={{ replace }}>
        <p>админка</p>
      </RoleGuard>,
    )

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/account'))
    expect(screen.queryByText('админка')).not.toBeInTheDocument()
  })

  it('пускает поддержку в раздел', async () => {
    const replace = vi.fn()
    stubApi('support')

    renderWithAuth(
      <RoleGuard router={{ replace }}>
        <p>админка</p>
      </RoleGuard>,
    )

    expect(await screen.findByText('админка')).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })
})
