import { createAuthClient, createTokenStore, detectLanguage, type Language } from '@repibot/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, type ReactNode, useContext, useMemo } from 'react'

import { preferredLanguages } from './telegram'

/**
 * Базовый URL пустой: MiniApp и API стоят за одним nginx, а абсолютный адрес
 * в сборке потребовал бы пересборки под каждое развёртывание.
 */
export const API_BASE_URL = ''

/**
 * Хранилище токена — один экземпляр на приложение, а не часть провайдера:
 * токен в него кладёт обмен initData, который случается до отрисовки React.
 */
export const tokenStore = createTokenStore()

type ApiClient = ReturnType<typeof createAuthClient>

const ApiContext = createContext<ApiClient | null>(null)

/**
 * Свой провайдер вместо `AuthProvider` из @repibot/core: тот заводит
 * хранилище токена внутри себя и наружу не отдаёт, а MiniApp получает токен
 * сам — обменом initData, без refresh-cookie.
 */
export function ApiProvider({
  children,
  // Адрес переопределяется в тестах: jsdom берёт Request из Node, а тот
  // относительный путь разобрать не умеет — в браузере он разрешается сам.
  baseUrl = API_BASE_URL,
}: {
  children: ReactNode
  baseUrl?: string
}) {
  const client = useMemo(() => createAuthClient({ baseUrl, store: tokenStore }), [baseUrl])
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>
}

function useApi(): ApiClient {
  const client = useContext(ApiContext)
  if (client === null) throw new Error('ApiProvider не подключён')
  return client
}

export function useProfile() {
  const { api } = useApi()
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me')
      // Пустой ответ тоже считается ошибкой: экран без данных показать нечем,
      // а openapi-fetch отдаёт `undefined` и там, где тела просто нет.
      if (error || !data) throw error ?? new Error('пустой ответ /api/me')
      return data
    },
  })
}

export function useSaveProfile() {
  const { api } = useApi()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: { name: string | null; language: Language }) => {
      const { data, error } = await api.PATCH('/api/me', { body: input })
      if (error || !data) throw error ?? new Error('пустой ответ /api/me')
      return data
    },
    // Ответ мутации сразу становится кэшем профиля: после смены языка подписи
    // перерисовываются, не дожидаясь повторного запроса.
    onSuccess: (data) => queries.setQueryData(['me'], data),
  })
}

/**
 * Язык интерфейса. Сохранённый в профиле важнее предпочтений Telegram
 * и браузера: пользователь выбрал его сам.
 *
 * Хук подходит только экранам, которым профиль и так нужен: он подписывается
 * на тот же запрос и до входа сходил бы в API без токена.
 */
export function useLanguage(): Language {
  const profile = useProfile()
  return profile.data?.language ?? detectLanguage(preferredLanguages())
}
