import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import type { ButtonHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

const button = cva(
  'inline-flex items-center justify-center font-medium transition-colors disabled:pointer-events-none disabled:opacity-50',
  {
    // Цвет текста задаётся только здесь, в variant. Если задать его ещё и в
    // size, twMerge схлопнет конфликтующие утилиты группы text-color и оставит
    // последнюю — у secondary и ghost подпись стала бы белой на светлом фоне.
    variants: {
      variant: {
        primary: 'bg-accent text-on-accent hover:bg-accent-hover',
        secondary: 'border border-border-strong text-text hover:bg-surface-sunken',
        ghost: 'text-text-accent hover:bg-jade-mist',
      },
      size: {
        sm: 'h-8 px-3 text-sm rounded-sm',
        md: 'h-10 px-4 text-base rounded-md',
        lg: 'h-12 px-6 text-lg rounded-md',
      },
    },
    // Мелкая кнопка с заливкой получает тёмный текст: белый на Jade проходит
    // по контрасту только с 18-19 px. Раздел 7 бренд-бука. У secondary и ghost
    // заливки нет, поэтому исключение к ним не относится.
    compoundVariants: [{ variant: 'primary', size: 'sm', class: 'text-[#08150F]' }],
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {
  asChild?: boolean
}

export function Button({ className, variant, size, asChild, ...props }: ButtonProps) {
  const Component = asChild ? Slot : 'button'
  return <Component className={cn(button({ variant, size }), className)} {...props} />
}
