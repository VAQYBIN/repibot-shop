import { createMemoryHistory, RouterProvider } from '@tanstack/react-router'
import { act, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { tokenStore } from '../api'
import { useAuthState } from '../auth'
import { router } from '../router'
import { PROFILE, renderWithProviders, stubFetch } from '../test-utils'

/* Устройство подмены роутера то же, что в router.test.tsx: панель вкладок
   рисует Link из @tanstack/react-router, а он матчится только внутри
   настоящего RouterProvider — контекста без загруженного дерева маршрутов
   ему недостаточно. */
async function renderLayout() {
  // Роутер восстанавливает прокрутку при каждой загрузке; jsdom не умеет
  // scrollTo и без подмены роняет консоль ошибкой на каждый тест.
  vi.stubGlobal('scrollTo', vi.fn())
  useAuthState.setState({ state: 'ready' })
  stubFetch((request) => {
    const path = new URL(request.url).pathname
    if (path === '/api/me') return Response.json(PROFILE)
    if (path === '/api/me/orders') return Response.json([])
    return new Response(null, { status: 404 })
  })
  await act(async () => {
    router.update({ history: createMemoryHistory({ initialEntries: ['/app/'] }) })
    await router.load()
  })
  const view = renderWithProviders(<RouterProvider router={router} />)
  // Заголовок главной подтверждает, что маршрут внутри Outlet дождался
  // ответа профиля — до этого панель уже на экране, а проверять нечего.
  await screen.findByRole('heading')
  return view
}

afterEach(() => {
  vi.unstubAllGlobals()
  tokenStore.set(null)
  useAuthState.setState({ state: 'checking' })
})

describe('каркас MiniApp', () => {
  it('показывает пять вкладок', async () => {
    const view = await renderLayout()

    expect(screen.getAllByRole('link')).toHaveLength(5)
    view.unmount()
  })

  it('отмечает текущую вкладку для скринридера', async () => {
    const view = await renderLayout()

    expect(screen.getByRole('link', { current: 'page' })).toBeInTheDocument()
    view.unmount()
  })
})
