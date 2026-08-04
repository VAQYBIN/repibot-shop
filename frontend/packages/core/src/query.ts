import { QueryClient } from '@tanstack/react-query'

/**
 * Общие настройки кэша. Повторять запрос при ошибке авторизации бессмысленно —
 * токен от этого не появится.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: (failureCount, error) => {
          const status = (error as { status?: number }).status
          if (status === 401 || status === 403) return false
          return failureCount < 2
        },
      },
    },
  })
}
