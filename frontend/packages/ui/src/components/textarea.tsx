import type { TextareaHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean | undefined
}

export function Textarea({ className, invalid, ...props }: TextareaProps) {
  return (
    <textarea
      aria-invalid={invalid === true ? true : undefined}
      className={cn(
        'w-full rounded-md border bg-surface px-3 py-2 text-body text-text',
        'placeholder:text-text-muted',
        invalid === true ? 'border-danger' : 'border-border-subtle',
        'focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
