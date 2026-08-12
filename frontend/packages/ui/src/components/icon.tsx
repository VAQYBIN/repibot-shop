import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react'

export type { IconSvgElement }

export interface IconProps {
  icon: IconSvgElement
  /** 16 — рядом с мелким текстом, 20 — обычный, 24 — самостоятельная кнопка. */
  size?: 16 | 20 | 24
  className?: string | undefined
  /**
   * Название для скринридера. Без него иконка декоративна — и это верно
   * для подавляющего большинства мест, где рядом есть подпись словами.
   */
  title?: string | undefined
}

/**
 * Единственный вход к иконкам.
 *
 * Толщина обводки одна на все размеры: разнобой заметен, когда иконки стоят
 * рядом в меню. Цвет не задаётся вовсе — иконка наследует цвет текста, поэтому
 * отдельного токена под иконки в палитре нет и не нужно.
 */
export function Icon({ icon, size = 20, className, title }: IconProps) {
  const label = title === undefined ? { 'aria-hidden': true } : { role: 'img', 'aria-label': title }
  return (
    <HugeiconsIcon
      icon={icon}
      size={size}
      strokeWidth={1.5}
      color="currentColor"
      className={className}
      {...label}
    />
  )
}
