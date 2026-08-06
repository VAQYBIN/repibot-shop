'use client'

import { type InputHTMLAttributes, useState } from 'react'

import { cn } from '../lib/cn'
import { Input } from './input'

export interface PasswordInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  /** Подписи кнопки приходят из словаря приложения: пакет `ui` не знает о переводах. */
  showLabel?: string
  hideLabel?: string
}

/** Иконка декоративная: смысл кнопки несёт `aria-label`. */
function EyeIcon({ crossed }: { crossed: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z" />
      <circle cx="12" cy="12" r="3" />
      {crossed ? <path d="m4 4 16 16" /> : null}
    </svg>
  )
}

export function PasswordInput({
  className,
  showLabel = 'Показать пароль',
  hideLabel = 'Скрыть пароль',
  ...props
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false)

  return (
    <div className="relative">
      {/* Отступ справа освобождает место под кнопку, иначе текст уезжает под неё. */}
      <Input type={visible ? 'text' : 'password'} className={cn('pr-11', className)} {...props} />
      <button
        type="button"
        aria-label={visible ? hideLabel : showLabel}
        aria-pressed={visible}
        onClick={() => setVisible((current) => !current)}
        className={cn(
          'absolute inset-y-0 right-0 flex w-11 items-center justify-center',
          'rounded-md text-text-muted hover:text-text',
        )}
      >
        <EyeIcon crossed={visible} />
      </button>
    </div>
  )
}
