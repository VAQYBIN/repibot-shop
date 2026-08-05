import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from './schema'

/**
 * Клиент нашего API. Токен читается функцией, а не передаётся значением:
 * в MiniApp он живёт в памяти и меняется при переоткрытии приложения.
 */
export function createApiClient(baseUrl: string, getToken: () => string | null) {
  const client = createClient<paths>({ baseUrl })

  const auth: Middleware = {
    async onRequest({ request }) {
      const token = getToken()
      if (token) request.headers.set('Authorization', `Bearer ${token}`)
      return request
    },
  }

  client.use(auth)
  return client
}
