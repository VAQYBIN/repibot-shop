'use client'

import {
  errorMessageKey,
  type Language,
  type TranslationKey,
  translate,
  useAuthClient,
} from '@repibot/core'
import { startAuthentication, startRegistration } from '@simplewebauthn/browser'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

/**
 * Хуки passkey живут в приложении, а не в `packages/core`.
 *
 * `@simplewebauthn/browser` трогает `navigator.credentials`, которого в MiniApp
 * нет: Telegram открывает страницу во встроенном браузере, где WebAuthn
 * работает не везде. Класть в общий пакет то, чем пользуется одно приложение,
 * значит тянуть браузерный API в сборку MiniApp.
 */

/**
 * Ошибка операции с ключом → ключ словаря.
 *
 * Отмена окна выбора ключа приходит как `NotAllowedError` — тем же именем, что
 * и настоящий отказ аутентификатора. Показывать «ошибка» человеку, который
 * просто закрыл окно, незачем, поэтому отмена получает собственный ключ.
 */
export function passkeyErrorKey(error: unknown): TranslationKey {
  if (error instanceof Error && error.name === 'NotAllowedError') {
    return 'auth.error.passkey_cancelled'
  }
  const code = (error as { error?: { code?: string } } | undefined)?.error?.code
  return errorMessageKey(code)
}

/**
 * Ошибка операции с ключом → фраза для человека.
 *
 * `null` означает «показывать нечего»: окно выбора ключа закрыли, и это не
 * отказ, а передумали. Красный текст в ответ на такое действие человек читает
 * как поломку.
 */
export function passkeyErrorText(error: unknown, language: Language): string | null {
  const key = passkeyErrorKey(error)
  if (key === 'auth.error.passkey_cancelled') return null
  return translate(language, key)
}

/**
 * Параметры WebAuthn бэкенд отдаёт как есть: структура задана спецификацией
 * браузера, и описывать её своей схемой значит поддерживать копию чужого
 * стандарта на двух языках сразу.
 *
 * В схеме API это словарь `unknown`, поэтому оба перехода — параметры внутрь
 * аутентификатора и его ответ обратно в тело запроса — идут через `unknown`:
 * общих полей у словаря и типов библиотеки нет, и прямое приведение TypeScript
 * запрещает. Проверяет структуру аутентификатор, а следом бэкенд.
 */
type RegistrationOptions = Parameters<typeof startRegistration>[0]['optionsJSON']
type AuthenticationOptions = Parameters<typeof startAuthentication>[0]['optionsJSON']
type CredentialBody = Record<string, unknown>

export function usePasskeys() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['passkeys'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/passkeys')
      if (error) throw error
      return data
    },
  })
}

export function useAddPasskey() {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => {
      const options = await api.POST('/api/me/passkeys/options')
      if (!options.data) throw new Error('нет параметров')

      const credential = await startRegistration({
        optionsJSON: options.data.options as unknown as RegistrationOptions,
      })

      // Ошибка бросается как есть, без обёртки в Error с готовой фразой: иначе
      // отмена окна выбора ключа стала бы неотличима от отказа сервера, а её
      // показывать нельзя.
      const { error } = await api.POST('/api/me/passkeys', {
        body: { credential: credential as unknown as CredentialBody, name },
      })
      if (error) throw error
    },
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ['passkeys'] })
      // В профиле показано число ключей — без сброса оно отстанет на один.
      await queries.invalidateQueries({ queryKey: ['me'] })
    },
  })
}

export function useDeletePasskey() {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.DELETE('/api/me/passkeys/{passkey_id}', {
        params: { path: { passkey_id: id } },
      })
      if (error) throw error
    },
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ['passkeys'] })
      await queries.invalidateQueries({ queryKey: ['me'] })
    },
  })
}

export function usePasskeyLogin() {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const options = await api.POST('/api/auth/passkey/login/options')
      if (!options.data) throw new Error('нет параметров')

      const credential = await startAuthentication({
        optionsJSON: options.data.options as unknown as AuthenticationOptions,
      })

      const { data, error } = await api.POST('/api/auth/passkey/login/verify', {
        body: { credential: credential as unknown as CredentialBody },
      })
      if (error) throw error
      return data
    },
    // Профиль перезапрашивается после входа: прежний ответ относится к другому
    // пользователю или к его отсутствию.
    onSuccess: () => queries.invalidateQueries({ queryKey: ['me'] }),
  })
}
