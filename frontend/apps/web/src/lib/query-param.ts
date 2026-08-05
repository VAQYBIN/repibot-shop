'use client'

import { useEffect, useState } from 'react'

/**
 * Значение параметра строки запроса.
 *
 * Читается через `window`, а не через `useSearchParams`: параметр существует
 * только в браузере, а хук Next заставил бы обернуть страницу в Suspense ради
 * данных, которых на сервере всё равно нет.
 *
 * `undefined` — ещё не прочитали, `null` — параметра в ссылке нет. Различать
 * их обязательно: иначе страница успела бы показать ошибку «нет токена»
 * до того, как заглянула в адрес.
 */
export function useQueryParam(name: string): string | null | undefined {
  const [value, setValue] = useState<string | null | undefined>(undefined)

  useEffect(() => {
    setValue(new URLSearchParams(window.location.search).get(name))
  }, [name])

  return value
}
