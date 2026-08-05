import type { ReactNode } from 'react'

import { AccountShell } from '@/components/account-shell'

/**
 * Содержимое кабинета зависит от текущего пользователя, кэшировать разметку
 * нельзя. Настройка стоит в серверном сегменте и распространяется на все
 * страницы кабинета: сами страницы клиентские, и Next читает конфигурацию
 * сегмента именно отсюда.
 */
export const dynamic = 'force-dynamic'

export default function AccountLayout({ children }: { children: ReactNode }) {
  return <AccountShell>{children}</AccountShell>
}
