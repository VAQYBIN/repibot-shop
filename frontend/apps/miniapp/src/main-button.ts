/**
 * Хук главной кнопки Телеграма для экрана.
 *
 * У Телеграма кнопка одна на всё приложение — она переживает смену
 * маршрута. Хук сам снимает обработчик при уходе с экрана: иначе кнопка
 * предыдущего экрана нажималась бы уже на следующем.
 */
import { useEffect, useRef } from 'react'

import { applyMainButton, hasMainButton, hideMainButton, onMainButtonClick } from './telegram'

export function useMainButton(options: {
  text: string
  onClick: () => void
  visible?: boolean
  loading?: boolean
  disabled?: boolean
}): { supported: boolean } {
  const { text, onClick, visible = true, loading = false, disabled = false } = options
  // Обработчик держится в ref и ставится один раз: если передавать его
  // напрямую в onMainButtonClick при каждой перерисовке, каждая перерисовка
  // снимала бы и ставила обработчик заново, и вместе с этим мигала бы сама
  // кнопка.
  const onClickRef = useRef(onClick)
  onClickRef.current = onClick

  useEffect(() => {
    const off = onMainButtonClick(() => onClickRef.current())
    return () => {
      off()
      hideMainButton()
    }
    // Обработчик ставится один раз на весь жизненный цикл экрана: onClick
    // читается через ref, а не как зависимость, поэтому массив зависимостей
    // пуст намеренно.
  }, [])

  useEffect(() => {
    applyMainButton({ text, visible, loading, disabled })
  }, [text, visible, loading, disabled])

  return { supported: hasMainButton() }
}
