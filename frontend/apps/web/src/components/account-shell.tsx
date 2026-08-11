'use client'

import { useLogout } from '@repibot/core'
import { Button } from '@repibot/ui'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import type { ReactNode } from 'react'

import { Lockup } from '@/components/lockup'
import { useProfileLanguage, useTranslate } from '@/lib/i18n'
import { AuthGuard } from './auth-guard'

const LINKS = [
  { href: '/account', key: 'account.title' },
  { href: '/account/subscription', key: 'subscription.title' },
  { href: '/account/payments', key: 'payment.title' },
  { href: '/account/security', key: 'account.security' },
  { href: '/account/notifications', key: 'notifications.title' },
] as const

function AccountFrame({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const logout = useLogout()

  async function signOut() {
    await logout.mutateAsync()
    router.replace('/login')
  }

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-3xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between gap-4">
        <Lockup size={32} />
        <Button variant="ghost" size="sm" onClick={signOut} disabled={logout.isPending}>
          {t('account.logout')}
        </Button>
      </header>

      <nav aria-label={t('account.title')} className="flex flex-wrap gap-2">
        {LINKS.map((link) => {
          const current = pathname === link.href
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={current ? 'page' : undefined}
              className={
                current
                  ? 'rounded-md bg-jade-mist px-3 py-2 text-sm font-medium text-text-accent'
                  : 'rounded-md px-3 py-2 text-sm text-text-secondary hover:bg-surface-sunken'
              }
            >
              {t(link.key)}
            </Link>
          )
        })}
      </nav>

      {children}
    </div>
  )
}

/**
 * Каркас кабинета: сначала гейт, и только потом всё остальное.
 *
 * Навигация и выход живут внутри гейта намеренно: `useMe` за его пределами
 * ушёл бы в сеть без токена и получил бы 401 на каждой загрузке.
 */
export function AccountShell({ children }: { children: ReactNode }) {
  const router = useRouter()
  return (
    <AuthGuard router={router}>
      <AccountFrame>{children}</AccountFrame>
    </AuthGuard>
  )
}
