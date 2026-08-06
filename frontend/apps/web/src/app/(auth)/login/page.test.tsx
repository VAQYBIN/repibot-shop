import { startAuthentication } from '@simplewebauthn/browser'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithAuth } from '@/test/providers'
import LoginPage from './page'

// vi.mock поднимается выше импортов, поэтому мок роутера создаётся через
// vi.hoisted — иначе ссылка на replace окажется в мёртвой зоне.
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }))

// В jsdom нет navigator.credentials, поэтому аутентификатор подменяется целиком:
// проверяется поведение страницы, а не работа браузерного API.
vi.mock('@simplewebauthn/browser', () => ({
  startAuthentication: vi.fn(async () => ({ id: 'credential' })),
  startRegistration: vi.fn(),
}))

afterEach(() => {
  vi.unstubAllGlobals()
  replace.mockReset()
  // Адрес общий на весь файл: оставленный ?error= показал бы чужую ошибку
  // в следующем тесте.
  window.history.replaceState({}, '', '/login')
})

/**
 * Ответ о способах входа. Страница спрашивает его в первом кадре, поэтому
 * тестам про Telegram нужен именно он, а не общая заглушка на всё подряд.
 */
function stubMethods(methods: { telegram: boolean; passkey: boolean }) {
  const fetchMock = vi.fn(async (request: Request) => {
    if (request.url.endsWith('/api/auth/methods')) return Response.json(methods)
    return new Response(null, { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Ответы обоих запросов входа по ключу: параметры и проверка подписи. */
function stubPasskey() {
  const fetchMock = vi.fn(async (request: Request) => {
    if (request.url.endsWith('/api/auth/methods')) {
      return Response.json({ telegram: false, passkey: true })
    }
    if (request.url.endsWith('/api/auth/passkey/login/options')) {
      return Response.json({ options: { challenge: 'test' } })
    }
    if (request.url.endsWith('/api/auth/passkey/login/verify')) {
      return Response.json({ access_token: 'jwt', expires_in: 900 })
    }
    return new Response(null, { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('страница входа', () => {
  it('показывает ошибку формы до отправки запроса', async () => {
    const fetchMock = stubMethods({ telegram: false, passkey: true })
    renderWithAuth(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Почта'), { target: { value: 'не адрес' } })
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    // Заведомо неверные данные до сети не доходят. Проверяется именно вход:
    // список способов входа страница спрашивает всегда, ещё до формы.
    const loginCalls = fetchMock.mock.calls.filter(([request]) =>
      request.url.endsWith('/api/auth/login'),
    )
    expect(loginCalls).toHaveLength(0)
  })

  it('переводит код ошибки бэкенда во внятную фразу', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'invalid_credentials' } }, { status: 401 })),
    )
    renderWithAuth(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Почта'), { target: { value: 'user@example.org' } })
    fireEvent.change(screen.getByLabelText('Пароль'), {
      target: { value: 'совершенно обычный пароль' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }))

    await waitFor(() => {
      // Пользователь видит фразу, а не код: код — контракт для фронтенда.
      expect(screen.getByRole('alert').textContent).not.toContain('invalid_credentials')
    })
    expect(screen.getByRole('alert')).toHaveTextContent('Неверная почта или пароль')
  })

  it('после успешного входа уводит в кабинет', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ access_token: 'jwt', expires_in: 900 })),
    )
    renderWithAuth(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Почта'), { target: { value: 'user@example.org' } })
    fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'пароль подлиннее' } })
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }))

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/account'))
  })

  it('ведёт в Telegram ссылкой, а не запросом', async () => {
    stubMethods({ telegram: true, passkey: true })
    renderWithAuth(<LoginPage />)

    // Именно ссылка: дальше идёт цепочка редиректов на чужой домен, и пройти
    // она должна в адресной строке, а не внутри fetch.
    const link = await screen.findByRole('link', { name: 'Войти через Telegram' })
    expect(link).toHaveAttribute('href', '/api/auth/telegram/start')
  })

  it('не показывает вход через Telegram, когда он не настроен', async () => {
    const fetchMock = stubMethods({ telegram: false, passkey: true })
    renderWithAuth(<LoginPage />)

    // Ответ уже применён: ссылки нет не потому, что запрос не успел вернуться.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: /Telegram/ })).not.toBeInTheDocument()
    })
  })

  it('показывает ошибку, с которой вернул редирект из Telegram', async () => {
    stubMethods({ telegram: true, passkey: true })
    window.history.replaceState({}, '', '/login?error=telegram_unavailable')
    renderWithAuth(<LoginPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Вход через Telegram сейчас недоступен',
    )
  })

  it('вход по ключу уводит в кабинет', async () => {
    stubPasskey()
    renderWithAuth(<LoginPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Войти по ключу' }))

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/account'))
  })

  it('отмену окна выбора ключа не показывает ошибкой', async () => {
    stubPasskey()
    const cancelled = new Error('The operation either timed out or was not allowed')
    cancelled.name = 'NotAllowedError'
    vi.mocked(startAuthentication).mockRejectedValueOnce(cancelled)
    renderWithAuth(<LoginPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Войти по ключу' }))

    await waitFor(() => expect(startAuthentication).toHaveBeenCalled())
    // Человек просто закрыл окно: краснеть не за что, и в кабинет он не едет.
    await expect(screen.findByRole('alert')).rejects.toThrow()
    expect(replace).not.toHaveBeenCalled()
  })
})
