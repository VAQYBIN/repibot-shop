'use client'

import { type Language, useAuthClient } from '@repibot/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { errorText } from './i18n'

/**
 * Какие способы входа доступны в этом развёртывании.
 *
 * Вход через Telegram требует Client ID из BotFather. Показывать кнопку,
 * которая приведёт на страницу с ошибкой, хуже, чем не показывать её вовсе.
 */
export function useAuthMethods() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['auth-methods'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/auth/methods')
      if (error || !data) throw error ?? new Error('пустой ответ /api/auth/methods')
      return data
    },
    // Настройки развёртывания не меняются в течение сессии.
    staleTime: Number.POSITIVE_INFINITY,
  })
}

/**
 * Код привязки Telegram и готовая ссылка в чат бота.
 *
 * Кэшировать нечего: код одноразовый и живёт десять минут, поэтому это
 * мутация, а не запрос — новый код берут осознанным действием.
 */
export function useLinkCode(language: Language) {
  const { api } = useAuthClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/me/telegram/link-code')
      if (error || !data) throw new Error(errorText(error, language))
      return data
    },
  })
}

export function useUnlinkTelegram(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE('/api/me/telegram')
      if (error) throw new Error(errorText(error, language))
    },
    // В профиле лежит признак привязки и @username — без сброса карточка
    // осталась бы показывать снятый аккаунт.
    onSuccess: () => queries.invalidateQueries({ queryKey: ['me'] }),
  })
}
