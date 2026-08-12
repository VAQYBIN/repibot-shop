import { cn } from '../lib/cn'

export interface SkeletonProps {
  className?: string | undefined
}

/**
 * Заглушка на месте будущего содержимого.
 *
 * Размеров у неё своих нет: их задаёт место применения, потому что смысл
 * скелетона именно в том, чтобы повторить форму того, что появится. Пульсация
 * гаснет вместе с остальным движением — за это отвечает `motion-safe`.
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn('rounded-md bg-surface-sunken motion-safe:animate-pulse', className)}
    />
  )
}
