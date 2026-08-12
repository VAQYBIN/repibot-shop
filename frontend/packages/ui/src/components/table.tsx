import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export interface TableProps extends HTMLAttributes<HTMLTableElement> {
  /**
   * Подпись таблицы для скринридера. Обязательна: список без названия
   * читается как набор чисел неизвестно о чём.
   */
  caption: string
  children: ReactNode
}

/**
 * Плотная таблица.
 *
 * Прокрутка живёт на обёртке, а не на странице: иначе широкий столбец с
 * почтой уводит вбок всю разметку вместе с меню.
 */
export function Table({ caption, children, className, ...props }: TableProps) {
  return (
    <div className="overflow-x-auto rounded-md border border-border-subtle">
      <table className={cn('w-full border-collapse text-small', className)} {...props}>
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  )
}

export function TableHead({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  // Шапка закреплена: в списке на сотню строк заголовки столбцов нужны и внизу.
  return <thead className={cn('sticky top-0 bg-surface-sunken', className)} {...props} />
}

export function TableBody(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...props} />
}

export function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr className={cn('border-border-subtle border-b last:border-b-0', className)} {...props} />
  )
}

export function TableHeaderCell({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn('px-3 py-2 text-left font-medium text-text-secondary', className)}
      {...props}
    />
  )
}

export function TableCell({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('px-3 py-2 text-text', className)} {...props} />
}
