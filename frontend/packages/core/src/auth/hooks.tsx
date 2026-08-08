import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, type ReactNode, useContext, useMemo } from 'react'

import type { Language } from '../i18n/index'
import { createAuthClient } from './client'
import { messageFrom } from './errors'
import { createTokenStore, type TokenStore } from './store'

type AuthClient = ReturnType<typeof createAuthClient>

const AuthContext = createContext<AuthClient | null>(null)

export interface AuthProviderProps {
  children: ReactNode
  baseUrl?: string
  onSignedOut?: (() => void) | undefined
  store?: TokenStore
}

/**
 * Один клиент на приложение.
 *
 * Базовый URL по умолчанию пустой: веб, MiniApp и API стоят за одним nginx, и
 * абсолютный адрес в сборке потребовал бы пересборки под каждое развёртывание.
 *
 * Хранилище токена можно передать снаружи: MiniApp обменивает initData ещё до
 * отрисовки и кладёт токен сам. Без этого ему пришлось бы держать собственный
 * клиент и копии хуков, а смысл общего пакета — в том, что веб и MiniApp
 * ведут себя одинаково по построению, а не по дисциплине.
 */
export function AuthProvider({ children, baseUrl = '', onSignedOut, store }: AuthProviderProps) {
  const client = useMemo(
    () => createAuthClient({ baseUrl, store: store ?? createTokenStore(), onSignedOut }),
    [baseUrl, onSignedOut, store],
  )
  return <AuthContext.Provider value={client}>{children}</AuthContext.Provider>
}

export function useAuthClient(): AuthClient {
  const client = useContext(AuthContext)
  if (client === null) throw new Error('AuthProvider не подключён')
  return client
}

export function useMe() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me')
      // Пустой ответ тоже ошибка: openapi-fetch отдаёт undefined и там, где
      // тела просто нет, а экран без данных показать нечем.
      if (error || !data) throw error ?? new Error('пустой ответ /api/me')
      return data
    },
  })
}

export function useLogin(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: { email: string; password: string }) => {
      const { data, error } = await api.POST('/api/auth/login', { body: input })
      if (error) throw new Error(messageFrom(error, language))
      return data
    },
    // Профиль перезапрашивается после входа: прежний ответ относится к другому
    // пользователю или к его отсутствию.
    onSuccess: () => queries.invalidateQueries({ queryKey: ['me'] }),
  })
}

export function useRegister(language: Language) {
  const { api } = useAuthClient()
  return useMutation({
    mutationFn: async (input: { email: string; password: string; language: Language }) => {
      const { data, error } = await api.POST('/api/auth/register', { body: input })
      if (error) throw new Error(messageFrom(error, language))
      return data
    },
  })
}

export function useLogout() {
  const client = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: () => client.signOut(),
    onSuccess: () => queries.clear(),
  })
}

export function useUpdateProfile(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: { name: string | null; language: Language }) => {
      const { data, error } = await api.PATCH('/api/me', { body: input })
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: (data) => queries.setQueryData(['me'], data),
  })
}

/**
 * Запрос смены адреса почты. Для аккаунта без почты — её добавление.
 *
 * Профиль намеренно не сбрасывается: адрес меняется только после перехода по
 * ссылке из письма, и обновлённый ответ показал бы новый адрес раньше времени.
 */
export function useRequestEmailChange(language: Language) {
  const { api } = useAuthClient()
  return useMutation({
    mutationFn: async (email: string) => {
      const { data, error } = await api.POST('/api/me/email/change-request', { body: { email } })
      if (error) throw new Error(messageFrom(error, language))
      return data
    },
  })
}

export function useSessions() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/sessions')
      if (error) throw error
      return data
    },
  })
}

export function useRevokeSession(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await api.DELETE('/api/me/sessions/{session_id}', {
        params: { path: { session_id: id } },
      })
      if (error) throw new Error(messageFrom(error, language))
    },
    onSuccess: () => queries.invalidateQueries({ queryKey: ['sessions'] }),
  })
}
