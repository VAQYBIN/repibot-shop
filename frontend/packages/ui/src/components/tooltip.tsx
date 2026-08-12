'use client'

import * as RadixTooltip from '@radix-ui/react-tooltip'
import type { ReactElement } from 'react'

import { cn } from '../lib/cn'

export const TooltipProvider = RadixTooltip.Provider

export interface TooltipProps {
  label: string
  children: ReactElement
  className?: string | undefined
}

/**
 * Подпись к кнопке, у которой осталась одна иконка.
 *
 * Частей наружу не выставляем: применение ровно одно, и набор из четырёх
 * кусочков здесь означал бы четыре способа собрать одно и то же.
 */
export function Tooltip({ label, children, className }: TooltipProps) {
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild aria-label={label}>
        {children}
      </RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          sideOffset={6}
          className={cn(
            'rounded-sm bg-text px-2 py-1 text-caption text-bg shadow-[var(--rp-shadow)]',
            className,
          )}
        >
          {label}
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  )
}
