import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import { AdminShell } from './admin-shell'

// vi.mock поднимается выше импортов, поэтому и роутер, и адрес открытой
// страницы создаются через vi.hoisted: иначе ссылки на них окажутся в мёртвой
// зоне. Адрес меняется по тесту, поэтому лежит в изменяемом объекте.
const nav = vi.hoisted(() => ({ replace: vi.fn(), pathname: '/admin' }))
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => nav.pathname,
}))

afterEach(() => {
  nav.replace.mockClear()
  nav.pathname = '/admin'
  vi.unstubAllGlobals()
})

function show(role: string) {
  return renderWithProviders(
    <AdminShell>
      <p>содержимое раздела</p>
    </AdminShell>,
    {
      handlers: {
        '/api/auth/refresh': { access_token: 'jwt', expires_in: 900 },
        '/api/me': { id: 1, role, email: 'staff@example.com' },
      },
    },
  )
}

function menu() {
  return screen.findByRole('navigation', { name: 'Разделы админки' })
}

describe('оболочка админки', () => {
  it('не показывает поддержке разделы про деньги', async () => {
    // Меню — не защита, но лишняя ссылка ведёт сотрудника на страницу,
    // которая ответит отказом: это не забота, а раздражение.
    show('support')

    const links = within(await menu()).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual(['Пользователи', 'Обращения'])
  })

  it('показывает администратору все разделы', async () => {
    show('admin')

    const links = within(await menu()).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual([
      'Сводка',
      'Пользователи',
      'Обращения',
      'Платежи',
      'Рассылки',
      'Ноды',
    ])
    expect(await screen.findByText('содержимое раздела')).toBeInTheDocument()
  })

  it('помечает открытый раздел', async () => {
    nav.pathname = '/admin/tickets'
    show('admin')

    const inside = within(await menu())
    expect(inside.getByRole('link', { name: 'Обращения' })).toHaveAttribute('aria-current', 'page')
    expect(inside.getByRole('link', { name: 'Сводка' })).not.toHaveAttribute('aria-current')
  })

  it('показывает, под кем вошёл сотрудник', async () => {
    show('admin')

    expect(await screen.findByText('staff@example.com')).toBeInTheDocument()
  })

  it('даёт выйти', async () => {
    /* До этой правки выйти из админки было нельзя вообще: кнопки не было
       ни на одном из семи экранов. */
    show('admin')

    expect(await screen.findByRole('button', { name: /выйти/i })).toBeInTheDocument()
  })
})
