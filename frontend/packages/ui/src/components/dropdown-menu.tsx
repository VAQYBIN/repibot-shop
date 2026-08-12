'use client'

import * as RadixMenu from '@radix-ui/react-dropdown-menu'
import type { ComponentPropsWithoutRef } from 'react'

import { cn } from '../lib/cn'

export const DropdownMenu = RadixMenu.Root
export const DropdownMenuTrigger = RadixMenu.Trigger

export function DropdownMenuContent({
  className,
  sideOffset = 6,
  ...props
}: ComponentPropsWithoutRef<typeof RadixMenu.Content>) {
  return (
    <RadixMenu.Portal>
      <RadixMenu.Content
        sideOffset={sideOffset}
        className={cn(
          // Меню действительно висит над страницей — здесь тень уместна,
          // в отличие от карточки, которая лежит в потоке.
          'min-w-44 rounded-md border border-border-subtle bg-surface p-1',
          'shadow-[var(--rp-shadow)]',
          className,
        )}
        {...props}
      />
    </RadixMenu.Portal>
  )
}

export interface DropdownMenuItemProps extends ComponentPropsWithoutRef<typeof RadixMenu.Item> {
  tone?: 'default' | 'danger' | undefined
}

export function DropdownMenuItem({ className, tone, ...props }: DropdownMenuItemProps) {
  return (
    <RadixMenu.Item
      className={cn(
        'cursor-pointer rounded-sm px-3 py-2 text-small outline-none',
        'data-[highlighted]:bg-surface-sunken',
        tone === 'danger' ? 'text-danger' : 'text-text',
        className,
      )}
      {...props}
    />
  )
}

export function DropdownMenuSeparator({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixMenu.Separator>) {
  return <RadixMenu.Separator className={cn('my-1 h-px bg-border-subtle', className)} {...props} />
}
