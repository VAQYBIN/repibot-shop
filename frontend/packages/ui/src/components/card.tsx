import type { HTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-lg border border-border-subtle bg-surface p-6 shadow-[var(--rp-shadow-sm)]',
        className,
      )}
      {...props}
    />
  )
}
