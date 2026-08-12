import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminPage from './page'

// vi.mock поднимается выше импортов, поэтому мок роутера создаётся через
// vi.hoisted — иначе ссылка на replace окажется в мёртвой зоне.
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }))

afterEach(() => {
  replace.mockClear()
  vi.unstubAllGlobals()
})

function show(role: string) {
  return renderWithProviders(<AdminPage />, {
    handlers: { '/api/me': { id: 1, role } },
  })
}

describe('главная админки', () => {
  it('уводит поддержку к пользователям', async () => {
    // Сотруднику поддержки сводка не положена, а пустая главная выглядела бы
    // поломкой: он попадает туда, ради чего и открыл админку.
    show('support')

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/admin/users'))
  })

  it('обещает администратору сводку', async () => {
    show('admin')

    expect(await screen.findByText(/Сводка появится/)).toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })
})
