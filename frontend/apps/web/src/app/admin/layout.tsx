import type { ReactNode } from 'react'

import { AdminShell } from '@/components/admin-shell'

/**
 * Раздел зависит от роли текущего пользователя, кэшировать разметку нельзя.
 * Настройка стоит в серверном сегменте: страницы раздела клиентские, и Next
 * читает конфигурацию сегмента отсюда.
 */
export const dynamic = 'force-dynamic'

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminShell>{children}</AdminShell>
}
