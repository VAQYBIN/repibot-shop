import { screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithAuth } from '@/test/providers'
import ConfirmEmailPage from './page'

afterEach(() => {
  vi.unstubAllGlobals()
  // Адрес общий на весь файл: оставленный токен попал бы в следующий тест.
  window.history.replaceState({}, '', '/confirm-email')
})

describe('страница подтверждения нового адреса', () => {
  it('подтверждает адрес одним публичным запросом, без входа', async () => {
    // Аргумент объявлен ради проверки адреса запроса ниже: у мока без
    // параметров тип вызова пустой и обращаться к нему нечем.
    const fetchMock = vi.fn(async (_request: Request) => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    window.history.replaceState({}, '', '/confirm-email?token=raw-token')

    renderWithAuth(<ConfirmEmailPage />)

    expect(await screen.findByText('Новый адрес подтверждён')).toBeInTheDocument()
    // Ровно один запрос: страница не пытается обновить сессию, потому что
    // письмо открывают в браузере с почтой, а не в том, где открыт кабинет.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[0].url).toContain('/api/auth/email/change-confirm')
  })

  it('после успеха предлагает вход и кабинет', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 204 })),
    )
    window.history.replaceState({}, '', '/confirm-email?token=raw-token')

    renderWithAuth(<ConfirmEmailPage />)

    expect(await screen.findByRole('link', { name: 'Войти с новым адресом' })).toHaveAttribute(
      'href',
      '/login',
    )
    expect(screen.getByRole('link', { name: 'Перейти в кабинет' })).toHaveAttribute(
      'href',
      '/account',
    )
  })

  it('без токена в ссылке говорит об этом и в сеть не ходит', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    renderWithAuth(<ConfirmEmailPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ссылка недействительна или устарела',
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('показывает причину отказа бэкенда', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'email_taken' } }, { status: 409 })),
    )
    window.history.replaceState({}, '', '/confirm-email?token=raw-token')

    renderWithAuth(<ConfirmEmailPage />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Этот адрес уже занят')
    })
  })
})
