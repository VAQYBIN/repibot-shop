import { createMemoryHistory, RouterContextProvider, RouterProvider } from '@tanstack/react-router'
import { act, configure, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { tokenStore } from '../api'
import { useAuthState } from '../auth'
import { router } from '../router'
import { PROFILE, renderWithProviders, stubFetch } from '../test-utils'
import { Winback } from './winback'

/**
 * Тот самый двойной монтаж, ради которого экран защищается от второго запроса.
 * Настройка идёт через configure, а не своим `<StrictMode>` в разметке: React
 * повторяет эффекты только когда строгий режим объявлен на корне дерева.
 */
configure({ reactStrictMode: true })

/** Запросы начисления, дошедшие до сети: их число — суть половины проверок. */
const claims: Request[] = []

/** Ответ на начисление задаёт сам тест; остальное экрану нужно лишь для языка. */
function stub(claim: (request: Request) => Response) {
  // Язык до ответа профиля берётся из предпочтений Telegram, а jsdom без них
  // сообщает en-US: без подмены первый кадр экрана был бы английским.
  vi.stubGlobal('Telegram', { WebApp: { initDataUnsafe: { user: { language_code: 'ru' } } } })
  vi.stubGlobal('scrollTo', vi.fn())
  stubFetch((request) => {
    const path = new URL(request.url).pathname
    if (path === '/api/me') return Response.json(PROFILE)
    if (path === '/api/me/orders') return Response.json([])
    if (path === '/api/winback/claim') {
      claims.push(request.clone())
      return claim(request)
    }
    return new Response(null, { status: 404 })
  })
}

/**
 * Экран без роутера, но с его контекстом: ссылке на подписку контекст нужен, а
 * матчи роутера рисуются внутри его Suspense — там монтаж уже не первый, и
 * строгий режим до экрана не дошёл бы.
 */
function show(token: string | null) {
  return renderWithProviders(
    <RouterContextProvider router={router}>
      <Winback token={token} />
    </RouterContextProvider>,
  )
}

beforeEach(() => {
  tokenStore.set('miniapp-token')
})

afterEach(() => {
  claims.length = 0
  vi.unstubAllGlobals()
  tokenStore.set(null)
  useAuthState.setState({ state: 'checking' })
})

describe('подарочные дни в Mini App', () => {
  it('начисляет дни по токену и говорит, сколько их', async () => {
    stub(() => Response.json({ days: 3 }))

    show('raw-token')

    expect(await screen.findByText('Готово. Дней добавлено: 3')).toBeVisible()
    expect(await claims[0]?.json()).toEqual({ token: 'raw-token' })
  })

  it('не сжигает одноразовый токен вторым запросом при двойном монтаже', async () => {
    // Повторный запрос по тому же токену сервер отвергает: без защиты человек
    // увидел бы «ссылка недействительна» вместо только что начисленных дней.
    stub(() =>
      claims.length > 1
        ? Response.json({ error: { code: 'invalid_token', message: '' } }, { status: 400 })
        : Response.json({ days: 3 }),
    )

    show('raw-token')

    expect(await screen.findByText('Готово. Дней добавлено: 3')).toBeVisible()
    expect(claims).toHaveLength(1)
  })

  it('на отвергнутый токен отвечает понятной ошибкой', async () => {
    stub(() => Response.json({ error: { code: 'invalid_token', message: '' } }, { status: 400 }))

    show('stale-token')

    expect(await screen.findByText('Ссылка недействительна или уже использована')).toBeVisible()
  })

  it('без токена в ссылке в сеть не ходит', async () => {
    stub(() => Response.json({ days: 3 }))

    show(null)

    expect(await screen.findByText('В ссылке нет токена — откройте письмо ещё раз')).toBeVisible()
    expect(claims).toHaveLength(0)
  })

  it('берёт токен из строки запроса маршрута /winback', async () => {
    stub(() => Response.json({ days: 7 }))
    // Экран живёт под общим гейтом Mini App: без готового входа root показал бы
    // заглушку и до маршрута дело бы не дошло.
    useAuthState.setState({ state: 'ready' })
    await act(async () => {
      router.update({
        history: createMemoryHistory({ initialEntries: ['/app/winback?token=from-email'] }),
      })
      await router.load()
    })

    const view = renderWithProviders(<RouterProvider router={router} />)

    expect(await screen.findByText('Готово. Дней добавлено: 7')).toBeVisible()
    expect(await claims[0]?.json()).toEqual({ token: 'from-email' })
    view.unmount()
  })
})
