import type { TokenStore } from '@repibot/core'
import { create } from 'zustand'

import { API_BASE_URL, tokenStore } from './api'
import { readInitData } from './telegram'

export type AuthState = 'checking' | 'ready' | 'failed' | 'outside'

export interface AuthOptions {
  baseUrl: string
  store: TokenStore
}

/**
 * Обмен initData на access-токен.
 *
 * Refresh здесь не используется: cookie в стороннем контексте веб-версии
 * Telegram не выживает. Вместо продления берётся свежий initData — Telegram
 * отдаёт его при каждом открытии, и он всегда моложе суток.
 */
export async function exchangeInitData(
  { baseUrl, store }: AuthOptions,
  initData: string,
): Promise<boolean> {
  // Пустая строка означает открытие вне Telegram. Сетевой запрос здесь дал бы
  // невнятную ошибку вместо понятного «откройте через бота».
  if (!initData) return false

  const response = await fetch(`${baseUrl}/api/auth/telegram/miniapp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ init_data: initData }),
  })

  if (!response.ok) {
    store.set(null)
    return false
  }

  const body = (await response.json()) as { access_token: string }
  store.set(body.access_token)
  return true
}

interface AuthStore {
  state: AuthState
  signIn: (options: AuthOptions) => Promise<void>
}

export const useAuthState = create<AuthStore>((set) => ({
  state: 'checking',
  async signIn(options) {
    const initData = readInitData()
    if (initData === null) {
      set({ state: 'outside' })
      return
    }
    set({ state: (await exchangeInitData(options, initData)) ? 'ready' : 'failed' })
  },
}))

/** Настройки обмена для самого приложения: одно хранилище токена на всех. */
export const telegramAuthOptions: AuthOptions = { baseUrl: API_BASE_URL, store: tokenStore }
