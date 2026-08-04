import type { InputHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-text',
        'placeholder:text-text-muted',
        // Кольцо от Jade Mist при фокусе — раздел 6 бренд-бука.
        'focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none',
        className,
      )}
      {...props}
    />
  )
}
