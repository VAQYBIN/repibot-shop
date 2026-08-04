import { createQueryClient } from '@repibot/core'
import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { router } from './router'
import './styles.css'
import { initTelegram } from './telegram'

initTelegram()

const container = document.getElementById('root')
if (!container) throw new Error('в разметке нет элемента #root')

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
