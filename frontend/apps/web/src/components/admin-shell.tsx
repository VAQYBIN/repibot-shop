'use client'

import { useMe } from '@repibot/core'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import type { ReactNode } from 'react'

import { RoleGuard } from './role-guard'

interface AdminLink {
  href: string
  label: string
  /** Роли, которым раздел показывается в меню. */
  roles: readonly string[]
}

/**
 * Разделы админки в порядке меню.
 *
 * «Пользователи» и «Ноды» появятся соседними планами; ссылки стоят уже сейчас,
 * потому что меню — предмет этой задачи, а не тех.
 */
const LINKS: readonly AdminLink[] = [
  { href: '/admin', label: 'Сводка', roles: ['admin'] },
  { href: '/admin/users', label: 'Пользователи', roles: ['admin', 'support'] },
  { href: '/admin/tickets', label: 'Обращения', roles: ['admin', 'support'] },
  { href: '/admin/payments', label: 'Платежи', roles: ['admin'] },
  { href: '/admin/broadcasts', label: 'Рассылки', roles: ['admin'] },
  { href: '/admin/nodes', label: 'Ноды', roles: ['admin'] },
]

/** Оболочка пускает обе роли; разграничение внутри делают сами страницы. */
const STAFF: readonly string[] = ['admin', 'support']

function AdminFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const me = useMe()
  const role = me.data?.role

  // Меню защитой не считается: скрытая ссылка ничего не запрещает, а роль
  // проверяют и страница, и маршрут API. Прятать нечего — незачем и дразнить
  // сотрудника разделом, который ответит ему отказом.
  const links = LINKS.filter((link) => role !== undefined && link.roles.includes(role))

  return (
    <div className="flex min-h-dvh flex-col bg-surface-sunken md:flex-row">
      <nav
        aria-label="Разделы админки"
        className="flex gap-2 overflow-x-auto border-border-subtle border-b bg-surface p-3 md:w-56 md:shrink-0 md:flex-col md:overflow-x-visible md:border-r md:border-b-0 md:p-4"
      >
        {links.map((link) => {
          const current = pathname === link.href
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={current ? 'page' : undefined}
              className={
                current
                  ? 'whitespace-nowrap rounded-md bg-jade-mist px-3 py-2 font-medium text-sm text-text-accent'
                  : 'whitespace-nowrap rounded-md px-3 py-2 text-sm text-text-secondary hover:bg-surface-sunken'
              }
            >
              {link.label}
            </Link>
          )
        })}
      </nav>

      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

/**
 * Каркас админки: сначала гейт, и только потом меню.
 *
 * Меню живёт внутри гейта намеренно: `useMe` за его пределами ушёл бы в сеть
 * без токена и получил бы 401 на каждой загрузке.
 */
export function AdminShell({ children }: { children: ReactNode }) {
  const router = useRouter()
  return (
    <RoleGuard router={router} allow={STAFF}>
      <AdminFrame>{children}</AdminFrame>
    </RoleGuard>
  )
}
