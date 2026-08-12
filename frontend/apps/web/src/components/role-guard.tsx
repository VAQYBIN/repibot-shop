'use client'

import { useMe } from '@repibot/core'
import { type ReactNode, useEffect } from 'react'

import { AuthGuard, type AuthGuardRouter } from './auth-guard'

export interface RoleGuardProps {
  children: ReactNode
  router: AuthGuardRouter
  /**
   * Роли, которым открыт раздел.
   *
   * Свойство обязательно: раздел без явного списка ролей — это раздел, о
   * правах которого забыли, а молчаливое «любой сотрудник» пускало бы
   * поддержку к деньгам.
   */
  allow: readonly string[]
}

function RoleCheck({ children, router, allow }: RoleGuardProps) {
  const me = useMe()
  const allowed = me.data !== undefined && allow.includes(me.data.role)

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
export function RoleGuard({ children, router, allow }: RoleGuardProps) {
  return (
    <AuthGuard router={router}>
      <RoleCheck router={router} allow={allow}>
        {children}
      </RoleCheck>
    </AuthGuard>
  )
}
