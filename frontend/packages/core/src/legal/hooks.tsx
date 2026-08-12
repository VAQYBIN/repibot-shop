import { useQuery } from '@tanstack/react-query'

import { useAuthClient } from '../auth/hooks'
import type { Language } from '../i18n/index'

/**
 * Опубликованные юридические документы.
 *
 * Пустой список — обычное состояние, а не сбой: набор документов заводит
 * администратор, и на свежем развёртывании их просто нет. Поэтому ошибки
 * запроса и пустой ответ должны различаться на стороне вызывающего.
 */
export function useLegalDocuments(language: Language) {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['legal', language],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/legal', {
        params: { query: { locale: language } },
      })
      if (error || !data) throw error ?? new Error('пустой ответ /api/legal')
      return data
    },
    // Документы меняются раз в год: перезапрашивать их при каждом
    // возвращении на вкладку незачем.
    staleTime: 5 * 60 * 1000,
  })
}
