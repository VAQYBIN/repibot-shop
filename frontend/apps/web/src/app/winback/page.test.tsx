import { configure, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import WinbackPage from './page'

// vi.mock поднимается выше импортов, поэтому мок роутера создаётся через
// объявленную заранее ссылку.
const replace = vi.fn()
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }))

/**
 * Тот самый двойной монтаж, ради которого экран защищается от второго запроса.
 * Строгий режим объявляется на корне дерева: своим `<StrictMode>` внутри
 * разметки React повторный монтаж не устраивает.
 */
configure({ reactStrictMode: true })

const PROFILE = {
  id: 1,
  email: 'user@example.org',
  email_verified: true,
  telegram_username: null,
  name: null,
  language: 'ru',
  role: 'user',
  referral_code: 'ABC12345',
  has_password: true,
  has_telegram: false,
  passkey_count: 0,
}

/** Запросы начисления, дошедшие до сети: их число — суть половины проверок. */
const claims: Request[] = []

function show(claim: (request: Request) => Response) {
  return renderWithProviders(<WinbackPage />, {
    handlers: {
      // Гейт кабинета: дни начисляются на аккаунт, и он должен быть свой.
      '/api/auth/refresh': { access_token: 'jwt', expires_in: 900 },
      '/api/me': PROFILE,
      '/api/winback/claim': (request: Request) => {
        claims.push(request.clone())
        return claim(request)
      },
    },
  })
}

afterEach(() => {
  claims.length = 0
  replace.mockClear()
  vi.unstubAllGlobals()
  // Адрес общий на весь файл: оставленный токен попал бы в следующий тест.
  window.history.replaceState({}, '', '/winback')
})

describe('подарочные дни в кабинете', () => {
  it('начисляет дни по токену из ссылки и говорит, сколько их', async () => {
    window.history.replaceState({}, '', '/winback?token=raw-token')

    show(() => Response.json({ days: 3 }))

    expect(await screen.findByText('Готово. Дней добавлено: 3')).toBeVisible()
    expect(await claims[0]?.json()).toEqual({ token: 'raw-token' })
  })

  it('не сжигает одноразовый токен вторым запросом при двойном монтаже', async () => {
    window.history.replaceState({}, '', '/winback?token=raw-token')

    // Повторный запрос по тому же токену сервер отвергает: без защиты человек
    // увидел бы «ссылка недействительна» вместо только что начисленных дней.
    show(() =>
      claims.length > 1
        ? Response.json({ error: { code: 'invalid_token', message: '' } }, { status: 400 })
        : Response.json({ days: 3 }),
    )

    expect(await screen.findByText('Готово. Дней добавлено: 3')).toBeVisible()
    expect(claims).toHaveLength(1)
  })

  it('на отвергнутый токен отвечает понятной ошибкой', async () => {
    window.history.replaceState({}, '', '/winback?token=stale-token')

    show(() => Response.json({ error: { code: 'invalid_token', message: '' } }, { status: 400 }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ссылка недействительна или уже использована',
    )
  })

  it('без токена в ссылке в сеть не ходит', async () => {
    show(() => Response.json({ days: 3 }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'В ссылке нет токена — откройте письмо ещё раз',
    )
    expect(claims).toHaveLength(0)
  })

  it('уводит на вход, когда сессии в этом браузере нет', async () => {
    window.history.replaceState({}, '', '/winback?token=raw-token')

    renderWithProviders(<WinbackPage />, {
      handlers: {
        '/api/auth/refresh': { status: 401, body: undefined },
        '/api/winback/claim': (request: Request) => {
          claims.push(request.clone())
          return Response.json({ days: 3 })
        },
      },
    })

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/login'))
    // Начисление до входа ушло бы в чужой аккаунт или в никуда.
    expect(claims).toHaveLength(0)
  })
})
