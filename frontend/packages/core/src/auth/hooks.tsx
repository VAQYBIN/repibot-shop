import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, type ReactNode, useContext, useMemo } from 'react'

import { type Language, type TranslationKey, translate } from '../i18n/index'
import { createAuthClient } from './client'
import { createTokenStore } from './store'

type AuthClient = ReturnType<typeof createAuthClient>

const AuthContext = createContext<AuthClient | null>(null)

export interface AuthProviderProps {
  children: ReactNode
  baseUrl?: string
  onSignedOut?: () => void
}

/**
 * Один клиент на приложение.
 *
 * Базовый URL по умолчанию пустой: веб, MiniApp и API стоят за одним nginx, и
 * абсолютный адрес в сборке потребовал бы пересборки под каждое развёртывание.
 */
export function AuthProvider({ children, baseUrl = '', onSignedOut }: AuthProviderProps) {
  const client = useMemo(
    () => createAuthClient({ baseUrl, store: createTokenStore(), onSignedOut }),
    [baseUrl, onSignedOut],
  )
  return <AuthContext.Provider value={client}>{children}</AuthContext.Provider>
}

export function useAuthClient(): AuthClient {
  const client = useContext(AuthContext)
  if (client === null) throw new Error('AuthProvider не подключён')
  return client
}

/** Код ошибки бэкенда → ключ словаря. Незнакомый код не должен давать пустоту. */
export function errorMessageKey(code: string | undefined): TranslationKey {
  const known: Record<string, TranslationKey> = {
    invalid_credentials: 'auth.error.invalid_credentials',
    email_not_verified: 'auth.error.email_not_verified',
    email_taken: 'auth.error.email_taken',
    weak_password: 'auth.error.weak_password',
    token_invalid: 'auth.error.token_invalid',
    rate_limited: 'auth.error.rate_limited',
  }
  return (code && known[code]) || 'auth.error.unknown'
}

function messageFrom(error: unknown, language: Language): string {
  const code = (error as { error?: { code?: string } })?.error?.code
  return translate(language, errorMessageKey(code))
}

export function useMe() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me')
      if (error) throw error
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
      if (error) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: (data) => queries.setQueryData(['me'], data),
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
