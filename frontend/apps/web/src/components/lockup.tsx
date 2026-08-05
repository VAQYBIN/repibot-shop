import Image from 'next/image'

import { Wordmark } from './wordmark'

/**
 * Горизонтальный лок-ап: знак слева, вордмарк справа.
 * Просвет равен высоте строчной буквы — раздел 5 бренд-бука.
 * Плашка меняется вместе с темой: на светлой — Jade, на тёмной — Ink.
 */
export function Lockup({ size = 40 }: { size?: number }) {
  return (
    <div className="flex items-center gap-[0.5em]">
      <Image
        src="/brand/logo-light.png"
        alt=""
        width={size}
        height={size}
        className="rounded-lg dark:hidden"
      />
      <Image
        src="/brand/logo-dark.png"
        alt=""
        width={size}
        height={size}
        className="hidden rounded-lg dark:block"
      />
      <Wordmark className="text-3xl" />
    </div>
  )
}
