import type { ReactNode } from 'react'

/**
 * Отдельный сегмент админки. Проверка роли появится в подпроекте 1 —
 * сейчас это только каркас, и снаружи он не опубликован.
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-dvh bg-surface-sunken">{children}</div>
}
