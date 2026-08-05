import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from '../api/schema'
import type { TokenStore } from './store'

const REFRESH_PATH = '/api/auth/refresh'

export interface AuthClientOptions {
  baseUrl: string
  store: TokenStore
  // `| undefined` обязателен из-за exactOptionalPropertyTypes: провайдер
  // прокидывает сюда необязательный проп, и без этого явное undefined не
  // проходит проверку типов.
  onSignedOut?: (() => void) | undefined
}

/**
 * Клиент API, умеющий обновлять просроченный access-токен.
 *
 * Обновление single-flight: параллельные запросы ждут один и тот же вызов
 * refresh. Иначе каждый из них ротирует токен, и сервер, увидев повторное
 * использование предыдущего, отзовёт сессию целиком.
 */
export function createAuthClient({ baseUrl, store, onSignedOut }: AuthClientOptions) {
  const client = createClient<paths>({ baseUrl, credentials: 'include' })
  let inFlight: Promise<boolean> | null = null

  async function refresh(): Promise<boolean> {
    // Запрос собирается как Request, а не парой «строка плюс init»: остальные
    // вызовы fetch в модуле идут через Request, и подмена fetch в тестах видит
    // один и тот же тип аргумента.
    const request = new Request(`${baseUrl}${REFRESH_PATH}`, {
      method: 'POST',
      credentials: 'include',
    })
    const response = await fetch(request)
    if (!response.ok) {
      store.set(null)
      onSignedOut?.()
      return false
    }
    const body = (await response.json()) as { access_token: string }
    store.set(body.access_token)
    return true
  }

  function refreshOnce(): Promise<boolean> {
    inFlight ??= refresh().finally(() => {
      inFlight = null
    })
    return inFlight
  }

  const auth: Middleware = {
    async onRequest({ request }) {
      const token = store.get()
      if (token) request.headers.set('Authorization', `Bearer ${token}`)
      return request
    },
    async onResponse({ request, response }) {
      // Ответ 401 самого обновления обрабатывать нечем: рекурсия здесь дала бы
      // бесконечный цикл запросов.
      if (response.status !== 401 || request.url.endsWith(REFRESH_PATH)) return response
      if (!(await refreshOnce())) return response

      const retry = new Request(request, {
        headers: new Headers(request.headers),
      })
      retry.headers.set('Authorization', `Bearer ${store.get() ?? ''}`)
      return fetch(retry)
    },
  }

  client.use(auth)

  return {
    api: client,
    refresh: refreshOnce,
    async signOut() {
      await client.POST('/api/auth/logout')
      store.set(null)
      onSignedOut?.()
    },
  }
}
