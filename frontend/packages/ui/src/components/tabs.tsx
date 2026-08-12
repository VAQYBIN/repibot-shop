'use client'

import * as RadixTabs from '@radix-ui/react-tabs'
import type { ComponentPropsWithoutRef } from 'react'

import { cn } from '../lib/cn'

export const Tabs = RadixTabs.Root

export function TabsList({ className, ...props }: ComponentPropsWithoutRef<typeof RadixTabs.List>) {
  return (
    <RadixTabs.List
      className={cn('inline-flex gap-1 rounded-md bg-surface-sunken p-1', className)}
      {...props}
    />
  )
}

export function TabsTrigger({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.Trigger>) {
  return (
    <RadixTabs.Trigger
      className={cn(
        'rounded-sm px-3 py-1.5 text-small text-text-secondary transition-colors',
        'hover:text-text',
        // Выбранная вкладка поднимается на поверхность из утопленной подложки:
        // так видно, что это переключатель, а не набор ссылок.
        'data-[state=active]:bg-surface data-[state=active]:font-medium data-[state=active]:text-text',
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.Content>) {
  return <RadixTabs.Content className={cn('mt-4', className)} {...props} />
}
