import type { SelectHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean | undefined
}

/**
 * Список остаётся нативным.
 *
 * Своё выпадающее решало бы одну задачу — вид, — и ломало бы три: набор
 * первых букв с клавиатуры, родное колесо выбора на телефоне и отправку
 * формы без обработчиков.
 */
export function Select({ className, invalid, ...props }: SelectProps) {
  return (
    <select
      aria-invalid={invalid === true ? true : undefined}
      className={cn(
        'h-10 w-full rounded-md border bg-surface px-3 text-body text-text',
        invalid === true ? 'border-danger' : 'border-border-subtle',
        'focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
