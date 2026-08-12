import type { CSSProperties, SVGProps } from 'react'

/**
 * Знак Re:Pibot.
 *
 * Обводка — currentColor, ядро — акцент темы, поэтому отдельного файла под
 * тёмную тему не нужно: цвет приходит из окружения.
 *
 * Геометрия продублирована из tools/brand/geometry.py. Дублирование
 * намеренное — интерфейс не должен зависеть от сборки файлов, — и оно
 * заперто тестом tools/tests/test_brand.py, который сверяет обе копии.
 */
const MARKS = {
  full: {
    viewBox: '0 0 109 97',
    path: 'M78.5 42.5 A24 24 0 0 1 30.5 42.5 A36 36 0 0 1 102.5 42.5 A48 48 0 0 1 6.5 42.5',
    core: { cx: 54.5, cy: 42.5, r: 8 },
    strokeWidth: 13,
  },
  // Ниже 32 px полный знак слипается: внутренний виток сходится с ядром.
  // Раздел 4 бренд-бука запрещает решать это уменьшением полной версии.
  small: {
    viewBox: '0 0 101 89',
    path: 'M32.5 38.5 A30 30 0 0 1 92.5 38.5 A42 42 0 0 1 8.5 38.5',
    core: { cx: 62.5, cy: 38.5, r: 10.5 },
    strokeWidth: 17,
  },
} as const

export type LogoMarkVariant = keyof typeof MARKS

export interface LogoMarkProps extends Omit<SVGProps<SVGSVGElement>, 'viewBox'> {
  variant?: LogoMarkVariant
  /**
   * Название для скринридера. Рядом с вордмарком знак декоративен — там
   * вызывающий передаёт aria-hidden, и название просто не читается.
   */
  title?: string
  /**
   * Вращение спирали при неподвижном ядре — фирменный прелоадер из раздела 6
   * бренд-бука. Режим живёт здесь, а не в `Spinner`, потому что центр
   * вращения — часть геометрии знака, а геометрия заперта в этом файле.
   */
  spinning?: boolean | undefined
}

export function LogoMark({
  variant = 'full',
  title = 'Re:Pibot',
  spinning,
  ...props
}: LogoMarkProps) {
  const mark = MARKS[variant]
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox={mark.viewBox} fill="none" {...props}>
      <title>{title}</title>
      <path
        d={mark.path}
        stroke="currentColor"
        strokeWidth={mark.strokeWidth}
        strokeLinecap="round"
        className={spinning ? 'rp-mark-spin' : undefined}
        style={
          spinning
            ? ({ '--rp-mark-origin': `${mark.core.cx}px ${mark.core.cy}px` } as CSSProperties)
            : undefined
        }
      />
      <circle cx={mark.core.cx} cy={mark.core.cy} r={mark.core.r} fill="var(--rp-accent)" />
    </svg>
  )
}
