import { type ClassValue, clsx } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * По умолчанию twMerge знает только встроенную шкалу Tailwind (xs, sm, base…)
 * — а она погашена в theme.css. Без этого расширения twMerge не узнаёт
 * `text-h3` как кегль и принимает его за цвет: `text-text-accent text-h3`
 * схлопывается в один класс, и подпись у ghost-кнопки остаётся без цвета.
 */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: ['display', 'h1', 'h2', 'h3', 'body', 'small', 'caption'],
    },
  },
})

export function cn(...classes: ClassValue[]): string {
  return twMerge(clsx(classes))
}
