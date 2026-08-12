import { screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import { AccountShell } from './account-shell'

// vi.mock поднимается выше импортов, поэтому открытый в тесте раздел заводится
// через vi.hoisted — иначе ссылка на него окажется в мёртвой зоне.
const location = vi.hoisted(() => ({ pathname: '/account/subscription' }))
vi.mock('next/navigation', () => ({
  usePathname: () => location.pathname,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

vi.mock('./auth-guard', () => ({
  AuthGuard: ({ children }: { children: ReactNode }) => children,
}))

vi.mock('@repibot/core', async () => ({
  ...(await vi.importActual<typeof import('@repibot/core')>('@repibot/core')),
  useLogout: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useMe: () => ({ data: { language: 'ru' } }),
}))

function show() {
  // Оболочка сама читает язык и тему из BrowserPreferencesProvider —
  // renderWithProviders уже его подключает, а простой render() из
  // @testing-library/react этого не делает и падает на useBrowserPreferences.
  return renderWithProviders(<AccountShell>содержимое</AccountShell>)
}

describe('AccountShell', () => {
  it('показывает все шесть разделов', () => {
    show()

    const nav = screen.getByRole('navigation')
    expect(screen.getAllByRole('link').filter((link) => nav.contains(link))).toHaveLength(6)
  })

  it('отмечает текущий раздел для скринридера, а не только краской', () => {
    show()

    expect(screen.getByRole('link', { current: 'page' })).toHaveAttribute(
      'href',
      '/account/subscription',
    )
  })

  it('даёт сменить тему изнутри кабинета', () => {
    /* До этой правки переключатель существовал только на странице-заглушке
       лендинга: вошедший человек сменить тему не мог нигде. */
    show()

    expect(screen.getByRole('button', { name: /тем/i })).toBeInTheDocument()
  })

  it('показывает содержимое страницы', () => {
    show()

    expect(screen.getByText('содержимое')).toBeInTheDocument()
  })
})
