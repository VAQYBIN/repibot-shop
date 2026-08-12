import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export type AlertTone = 'error' | 'warning' | 'success' | 'info'

export interface AlertProps {
  tone: AlertTone
  title?: string | undefined
  children: ReactNode
  className?: string | undefined
}

/* Подложка — тот же цвет с прозрачностью: отдельных «мягких» оттенков под
   каждый статус в палитре нет, а выдумывать их на глаз значит завести шестую
   шкалу цвета мимо бренд-бука. */
const TONES: Record<AlertTone, string> = {
  error: 'border-danger/40 bg-danger/8 text-text',
  warning: 'border-warning/40 bg-warning/8 text-text',
  success: 'border-success/40 bg-success/8 text-text',
  info: 'border-info/40 bg-info/8 text-text',
}

export function Alert({ tone, title, children, className }: AlertProps) {
  return (
    <div
      // Отказ перебивает, остальное ждёт очереди.
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn('rounded-md border px-4 py-3 text-small', TONES[tone], className)}
    >
      {title === undefined ? null : <p className="font-medium">{title}</p>}
      <div className={title === undefined ? undefined : 'mt-1 text-text-secondary'}>{children}</div>
    </div>
  )
}
