'use client'

import { useRouter } from 'next/navigation'
import type { ReactNode } from 'react'

import { RoleGuard } from './role-guard'

export function AdminShell({ children }: { children: ReactNode }) {
  const router = useRouter()
  return (
    <RoleGuard router={router}>
      <div className="min-h-dvh bg-surface-sunken">{children}</div>
    </RoleGuard>
  )
}
