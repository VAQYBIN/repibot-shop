'use client'

import { type ReactNode, useEffect, useId, useRef } from 'react'

import { cn } from '../lib/cn'

export interface DialogProps {
  open: boolean
  onClose: () => void
  title: string
  description?: string | undefined
  /** Кнопки подтверждения и отмены. */
  children: ReactNode
  className?: string | undefined
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function focusable(root: HTMLElement | null): HTMLElement[] {
  if (root === null) return []
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE))
}

/**
 * Модальное окно на нативной разметке.
 *
 * Radix Dialog в зависимостях пакета нет, а добавлять его ради одного окна
 * подтверждения дороже, чем написать ловушку фокуса: без неё Tab уходит
 * в разметку под окном, и пользователь клавиатуры остаётся без выхода.
 *
 * Закрытие — Escape или кнопка отмены; клик по подложке не обрабатывается,
 * чтобы не заводить интерактивный элемент без доступной роли.
 */
export function Dialog({ open, onClose, title, description, children, className }: DialogProps) {
  const panel = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const descriptionId = useId()

  useEffect(() => {
    if (!open) return

    // Фокус возвращается туда, откуда окно открыли: иначе после закрытия он
    // уезжает в начало страницы.
    const restore = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const initial = focusable(panel.current)[0] ?? panel.current
    initial?.focus()

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
        return
      }
      if (event.key !== 'Tab') return

      const items = focusable(panel.current)
      const first = items[0]
      const last = items[items.length - 1]
      if (first === undefined || last === undefined) return

      const active = document.activeElement
      const inside = panel.current?.contains(active) === true
      if (event.shiftKey && (active === first || !inside)) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !inside)) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      restore?.focus()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-4">
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description === undefined ? undefined : descriptionId}
        tabIndex={-1}
        className={cn(
          'w-full max-w-md rounded-lg border border-border-subtle bg-surface p-6',
          'shadow-[var(--rp-shadow-lg)]',
          className,
        )}
      >
        <h2 id={titleId} className="text-h3 font-semibold text-text">
          {title}
        </h2>
        {description === undefined ? null : (
          <p id={descriptionId} className="mt-2 text-small text-text-secondary">
            {description}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-3">{children}</div>
      </div>
    </div>
  )
}
