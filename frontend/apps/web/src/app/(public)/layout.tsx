import type { ReactNode } from 'react'

import { PublicFooter } from '@/components/public-footer'
import { PublicHeader } from '@/components/public-header'

/**
 * Оболочка страниц, которые видит человек до входа.
 *
 * Группа в скобках не попадает в адрес: `/plans` и `/legal/terms` остались
 * там же, где были. Вход и регистрация сюда не входят намеренно — у них своя
 * центрированная компоновка, и шапка с подвалом её только растащили бы.
 */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-bg">
      <PublicHeader />
      <div className="flex-1">{children}</div>
      <PublicFooter />
    </div>
  )
}
