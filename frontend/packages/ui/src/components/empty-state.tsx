import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export interface EmptyStateProps {
  title: string
  description?: string | undefined
  /** Кнопка или ссылка: без неё пустое состояние остаётся тупиком. */
  action?: ReactNode
  className?: string | undefined
}

export function EmptyState({ title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-2 rounded-lg border border-dashed border-border-subtle',
        'bg-surface-sunken px-6 py-10 text-center',
        className,
      )}
    >
      <p className="font-medium text-text">{title}</p>
      {description === undefined ? null : (
        <p className="text-small text-text-secondary">{description}</p>
      )}
      {action === undefined ? null : <div className="mt-2">{action}</div>}
    </div>
  )
}
