'use client'

import {
  BubbleChatIcon,
  CreditCardIcon,
  LockIcon,
  Notification01Icon,
  ShieldKeyIcon,
  UserIcon,
} from '@hugeicons/core-free-icons'
import { useLogout } from '@repibot/core'
import { Button, cn, Icon } from '@repibot/ui'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import type { ReactNode } from 'react'

import { Lockup } from '@/components/lockup'
import { ThemeToggle } from '@/components/theme-toggle'
import { useProfileLanguage, useTranslate } from '@/lib/i18n'
import { AuthGuard } from './auth-guard'

const LINKS = [
  { href: '/account', key: 'account.title', icon: UserIcon },
  { href: '/account/subscription', key: 'subscription.title', icon: ShieldKeyIcon },
  { href: '/account/payments', key: 'payment.title', icon: CreditCardIcon },
  { href: '/account/security', key: 'account.security', icon: LockIcon },
  { href: '/account/notifications', key: 'notifications.title', icon: Notification01Icon },
  { href: '/account/support', key: 'support.title', icon: BubbleChatIcon },
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
    <div className="min-h-dvh bg-bg">
      <header className="border-border-subtle border-b bg-surface">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <Lockup size={28} />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="ghost" size="sm" onClick={signOut} disabled={logout.isPending}>
              {t('account.logout')}
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 md:flex-row md:gap-8">
        <nav
          aria-label={t('account.title')}
          // Ниже md столбец схлопывается в полосу с прокруткой: шесть
          // разделов в колонку на телефоне съели бы весь первый экран.
          className="-mx-4 flex gap-1 overflow-x-auto px-4 md:mx-0 md:w-56 md:shrink-0 md:flex-col md:overflow-x-visible md:px-0"
        >
          {LINKS.map((link) => {
            const current = pathname === link.href
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={current ? 'page' : undefined}
                className={cn(
                  'flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-small transition-colors',
                  current
                    ? 'bg-jade-mist font-medium text-text-accent'
                    : 'text-text-secondary hover:bg-surface-sunken hover:text-text',
                )}
              >
                <Icon icon={link.icon} size={20} />
                {t(link.key)}
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
