import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

export interface BadgeProps {
  tone: BadgeTone
  children: ReactNode
  className?: string | undefined
}

const TONES: Record<BadgeTone, string> = {
  neutral: 'border-border-strong text-text-secondary',
  success: 'border-success/50 text-success',
  warning: 'border-warning/50 text-warning',
  danger: 'border-danger/50 text-danger',
  info: 'border-info/50 text-info',
}

/**
 * Статус словом в рамке.
 *
 * Заливки нет намеренно: в плотном списке десяток залитых плашек начинает
 * рябить сильнее, чем сами строки. Рамка отделяет статус от текста ровно
 * настолько, насколько нужно.
 */
export function Badge({ tone, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-caption',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
