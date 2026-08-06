'use client'

import { useAuthClient } from '@repibot/core'
import { type ReactNode, useEffect, useState } from 'react'

export interface AuthGuardRouter {
  replace: (href: string) => void
}

export interface AuthGuardProps {
  children: ReactNode
  /** Роутер передаётся снаружи, чтобы гейт можно было проверить без Next. */
  router: AuthGuardRouter
}

function AuthGuardSkeleton() {
  return (
    <div className="mx-auto w-full max-w-2xl p-6" aria-hidden="true">
      <div className="h-8 w-40 animate-pulse rounded-md bg-surface-sunken" />
      <div className="mt-4 h-32 animate-pulse rounded-lg bg-surface-sunken" />
    </div>
  )
}

/**
 * Гейт кабинета.
 *
 * Проверка клиентская: refresh-cookie ограничена путём /api/auth/refresh, и
 * серверные компоненты Next её не видят — так и задумано, вся защита от CSRF
 * держится на том, что cookie доступна одному эндпоинту.
 */
export function AuthGuard({ children, router }: AuthGuardProps) {
  const { refresh } = useAuthClient()
  const [state, setState] = useState<'checking' | 'ready'>('checking')

  useEffect(() => {
    let cancelled = false
    void refresh().then((ok) => {
      if (cancelled) return
      if (ok) setState('ready')
      else router.replace('/login')
    })
    return () => {
      cancelled = true
    }
  }, [refresh, router])

  if (state === 'checking') return <AuthGuardSkeleton />
  return <>{children}</>
}
