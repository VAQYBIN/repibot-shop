import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { messageFrom } from '../auth/errors'
import { useAuthClient } from '../auth/hooks'
import type { Language } from '../i18n/index'

const NOTIFICATIONS_QUERY_KEY = ['notification-settings'] as const

/**
 * Согласие на новости и предложения.
 *
 * В API это булево значение, хотя в базе лежит момент отказа: обратный знак
 * разворачивает сервер, и клиенту про отписку знать нечего.
 */
export function useNotificationSettings() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/notifications')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/notifications')
      return data
    },
  })
}

/**
 * Переключение согласия.
 *
 * Ответ кладётся в кэш напрямую: сервер вернул то самое состояние, и второй
 * запрос за ним ничего не уточнит.
 */
export function useUpdateNotificationSettings(language: Language = 'ru') {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (marketingEnabled: boolean) => {
      const { data, error } = await api.PATCH('/api/me/notifications', {
        body: { marketing_enabled: marketingEnabled },
      })
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: (data) => queries.setQueryData(NOTIFICATIONS_QUERY_KEY, data),
  })
}
