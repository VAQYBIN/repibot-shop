'use client'

import { useId } from 'react'

import { cn } from '../lib/cn'

export interface SwitchProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label: string
  id?: string | undefined
  disabled?: boolean | undefined
  className?: string | undefined
}

/**
 * Переключатель на нативном чекбоксе.
 *
 * Radix Switch в зависимостях пакета нет, а нативный `input` с ролью `switch`
 * даёт то же поведение бесплатно: клавиатура, форма и озвучивание состояния
 * работают без единой строки обработчиков.
 *
 * Компонент управляемый, поэтому `aria-checked` проставляется явно и всегда
 * совпадает с состоянием.
 */
export function Switch({ checked, onCheckedChange, label, id, disabled, className }: SwitchProps) {
  const generated = useId()
  const inputId = id ?? generated

  return (
    <div className={cn('flex items-center gap-3', className)}>
      <span className="relative inline-flex h-6 w-11 shrink-0 items-center">
        <input
          id={inputId}
          type="checkbox"
          role="switch"
          aria-checked={checked}
          checked={checked}
          disabled={disabled}
          onChange={(event) => onCheckedChange(event.target.checked)}
          className={cn(
            'peer h-6 w-11 cursor-pointer appearance-none rounded-full',
            'border border-border-strong bg-surface-sunken transition-colors',
            'checked:border-accent checked:bg-accent',
            'focus-visible:ring-3 focus-visible:ring-jade-mist focus-visible:outline-none',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        />
        {/* Ползунок декоративный: состояние читается с самого поля. */}
        <span
          aria-hidden="true"
          className={cn(
            'pointer-events-none absolute left-0.5 h-5 w-5 rounded-full bg-surface',
            'shadow-[var(--rp-shadow-sm)] transition-transform peer-checked:translate-x-5',
          )}
        />
      </span>
      <label htmlFor={inputId} className="text-small text-text">
        {label}
      </label>
    </div>
  )
}
