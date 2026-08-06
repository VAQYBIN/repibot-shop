'use client'

import { AuthProvider as CoreAuthProvider, createQueryClient } from '@repibot/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { type ReactNode, useState } from 'react'

/**
 * Клиент запросов и клиент API на всё приложение.
 *
 * Оба создаются один раз: новый QueryClient на каждый рендер обнулял бы кэш,
 * а новый AuthClient потерял бы access-токен, который живёт только в памяти.
 *
 * Базовый URL остаётся относительным (значение по умолчанию в `AuthProvider`):
 * веб и API стоят за одним nginx, и абсолютный адрес в сборке означал бы
 * пересборку под каждое развёртывание.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [queries] = useState(createQueryClient)

  return (
    <QueryClientProvider client={queries}>
      <CoreAuthProvider>{children}</CoreAuthProvider>
    </QueryClientProvider>
  )
}
