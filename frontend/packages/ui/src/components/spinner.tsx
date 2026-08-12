import { LogoMark } from './logo-mark'

export interface SpinnerProps {
  /** Сторона в пикселях. По умолчанию 24 — размер строки текста рядом. */
  size?: number
  /** Что именно грузится. Читается скринридером вместо картинки. */
  label?: string
  className?: string | undefined
}

/** Ниже этого размера полный знак слипается — раздел 4 бренд-бука. */
const SMALL_BELOW = 32

export function Spinner({ size = 24, label = 'Загрузка', className }: SpinnerProps) {
  return (
    <span role="status" aria-label={label} className={className}>
      <LogoMark
        variant={size < SMALL_BELOW ? 'small' : 'full'}
        spinning
        title={label}
        width={size}
        height={size}
        className="text-text-muted"
      />
    </span>
  )
}
