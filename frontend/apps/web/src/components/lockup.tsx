import { LogoMark } from '@repibot/ui'

import { Wordmark } from './wordmark'

// Кегль вордмарка относительно высоты знака — из утверждённого оригинала,
// те же числа в tools/brand/build.py.
const FONT_RATIO = 0.485
// Высота строчной x в Inter: 1118 из 2048 единиц. Раздел 5 задаёт просвет
// между знаком и надписью равным именно ей.
const X_HEIGHT_RATIO = 0.546

// Ниже этого размера полный знак слипается — раздел 4.
const SIMPLIFIED_BELOW = 32

/**
 * Горизонтальный лок-ап: знак слева, вордмарк справа.
 * Кегль и просвет считаются от высоты знака, поэтому пропорции держатся
 * на любом размере и совпадают с файлом docs/design/logo/logo-lockup-h.svg.
 */
export function Lockup({ size = 40 }: { size?: number }) {
  const fontSize = size * FONT_RATIO
  return (
    <div
      className="flex items-center text-text"
      style={{ fontSize, gap: fontSize * X_HEIGHT_RATIO }}
    >
      <LogoMark
        variant={size < SIMPLIFIED_BELOW ? 'small' : 'full'}
        style={{ height: size, width: 'auto' }}
        aria-hidden="true"
      />
      <Wordmark />
    </div>
  )
}
