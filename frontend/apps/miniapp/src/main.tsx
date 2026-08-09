import { AuthProvider, createQueryClient } from '@repibot/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { API_BASE_URL, tokenStore } from './api'
import { telegramAuthOptions, useAuthState } from './auth'
import { router } from './router'
import './styles.css'
import { initTelegram } from './telegram'

initTelegram()

// Обмен initData начинается до отрисовки: Telegram отдаёт свежий initData при
// каждом открытии, и ждать монтирования компонентов незачем.
void useAuthState.getState().signIn(telegramAuthOptions)

const container = document.getElementById('root')
if (!container) throw new Error('в разметке нет элемента #root')

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      {/* Хранилище общее для exchange и API-клиента. Root layout не
          монтирует Outlet, пока exchange не запишет токен и state не станет ready. */}
      <AuthProvider baseUrl={API_BASE_URL} store={tokenStore}>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
