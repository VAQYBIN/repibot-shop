'use client'

import {
  BubbleChatIcon,
  ChartLineData01Icon,
  CreditCardIcon,
  DocumentValidationIcon,
  Mail01Icon,
  ServerStack01Icon,
  UserGroupIcon,
} from '@hugeicons/core-free-icons'
import { useLogout, useMe } from '@repibot/core'
import { Button, Icon, type IconSvgElement } from '@repibot/ui'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import type { ReactNode } from 'react'

import { ThemeToggle } from '@/components/theme-toggle'
import { RoleGuard } from './role-guard'

interface AdminLink {
  href: string
  label: string
  /** Роли, которым раздел показывается в меню. */
  roles: readonly string[]
  icon: IconSvgElement
}

/**
 * Разделы админки в порядке меню.
 *
 * «Пользователи» и «Ноды» появятся соседними планами; ссылки стоят уже сейчас,
 * потому что меню — предмет этой задачи, а не тех.
 */
const LINKS: readonly AdminLink[] = [
  { href: '/admin', label: 'Сводка', roles: ['admin'], icon: ChartLineData01Icon },
  { href: '/admin/users', label: 'Пользователи', roles: ['admin', 'support'], icon: UserGroupIcon },
  { href: '/admin/tickets', label: 'Обращения', roles: ['admin', 'support'], icon: BubbleChatIcon },
  { href: '/admin/payments', label: 'Платежи', roles: ['admin'], icon: CreditCardIcon },
  { href: '/admin/broadcasts', label: 'Рассылки', roles: ['admin'], icon: Mail01Icon },
  { href: '/admin/nodes', label: 'Ноды', roles: ['admin'], icon: ServerStack01Icon },
  { href: '/admin/legal', label: 'Документы', roles: ['admin'], icon: DocumentValidationIcon },
]

/** Оболочка пускает обе роли; разграничение внутри делают сами страницы. */
const STAFF: readonly string[] = ['admin', 'support']

function AdminFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const me = useMe()
  const logout = useLogout()
  const role = me.data?.role

  // Меню защитой не считается: скрытая ссылка ничего не запрещает, а роль
  // проверяют и страница, и маршрут API. Прятать нечего — незачем и дразнить
  // сотрудника разделом, который ответит ему отказом.
  const links = LINKS.filter((link) => role !== undefined && link.roles.includes(role))
  const current = links.find((link) => link.href === pathname)

  async function signOut() {
    await logout.mutateAsync()
    router.replace('/login')
  }

  return (
    <div className="flex min-h-dvh flex-col bg-surface-sunken">
      <header className="flex items-center justify-between gap-4 border-border-subtle border-b bg-surface px-4 py-3">
        <span className="font-medium text-small text-text">{current?.label ?? 'Админка'}</span>
        <div className="flex items-center gap-3">
          {/* Почта, а не имя: в админке важно, под какой учётной записью
              сделано действие, а имя может совпасть у двух сотрудников. */}
          <span className="text-caption text-text-muted">{me.data?.email}</span>
          <ThemeToggle />
          <Button variant="ghost" size="sm" onClick={signOut} disabled={logout.isPending}>
            Выйти
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <nav
          aria-label="Разделы админки"
          className="flex gap-2 overflow-x-auto border-border-subtle border-b bg-surface p-3 md:w-56 md:shrink-0 md:flex-col md:overflow-x-visible md:border-r md:border-b-0 md:p-4"
        >
          {links.map((link) => {
            const active = pathname === link.href
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? 'page' : undefined}
                className={
                  active
                    ? 'flex items-center gap-2 whitespace-nowrap rounded-md bg-jade-mist px-3 py-2 font-medium text-small text-text-accent'
                    : 'flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-small text-text-secondary hover:bg-surface-sunken'
                }
              >
                <Icon icon={link.icon} size={20} />
                {link.label}
              </Link>
            )
          })}
        </nav>

        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  )
}

/**
 * Каркас админки: сначала гейт, и только потом шапка и меню.
 *
 * Шапка и меню живут внутри гейта намеренно: `useMe` за его пределами ушёл бы
 * в сеть без токена и получил бы 401 на каждой загрузке.
 */
export function AdminShell({ children }: { children: ReactNode }) {
  const router = useRouter()
  return (
    <RoleGuard router={router} allow={STAFF}>
      <AdminFrame>{children}</AdminFrame>
    </RoleGuard>
  )
}
