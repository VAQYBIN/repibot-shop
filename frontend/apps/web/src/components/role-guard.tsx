'use client'

import { useMe } from '@repibot/core'
import { type ReactNode, useEffect } from 'react'

import { AuthGuard, type AuthGuardRouter } from './auth-guard'

/** Роли, которым открыт раздел администрирования. */
const ALLOWED: readonly string[] = ['admin', 'support']

export interface RoleGuardProps {
  children: ReactNode
  router: AuthGuardRouter
}

function RoleCheck({ children, router }: RoleGuardProps) {
  const me = useMe()
  const allowed = me.data !== undefined && ALLOWED.includes(me.data.role)

  useEffect(() => {
    if (me.data !== undefined && !allowed) router.replace('/account')
  }, [allowed, me.data, router])

  if (me.isPending) return null
  // Разметка не показывается ни на миг: редирект асинхронный, и без этой
  // проверки чужой раздел успел бы мелькнуть на экране.
  if (!allowed) return null
  return <>{children}</>
}

/**
 * Гейт администрирования: сначала сессия, затем роль.
 *
 * Роль берётся из профиля, а не из access-токена: в claims её нет намеренно,
 * иначе понижение прав действовало бы только после истечения токена.
 */
export function RoleGuard({ children, router }: RoleGuardProps) {
  return (
    <AuthGuard router={router}>
      <RoleCheck router={router}>{children}</RoleCheck>
    </AuthGuard>
  )
}
