/**
 * Вордмарк. Двоеточие — отдельный элемент в цвете Jade: по бренд-буку это
 * часть марки, его нельзя убрать, заменить дефисом или перекрасить.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`font-medium tracking-[-0.03em] lowercase ${className ?? ''}`}>
      <span>re</span>
      <span className="text-accent">:</span>
      <span>pibot</span>
    </span>
  )
}
