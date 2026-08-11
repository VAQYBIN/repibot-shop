import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { PROFILE, renderWithProviders, stubFetch, withRussianLocale } from '../test-utils'
import { Profile } from './profile'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('профиль MiniApp', () => {
  it('показывает имя, реферальный код и текущий язык', async () => {
    stubFetch(() => Response.json(PROFILE))

    renderWithProviders(<Profile />)

    expect(await screen.findByText('Аня')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Профиль' })).toBeInTheDocument()
    expect(screen.getByText('RP-ABC123')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Русский' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('переключение языка отправляет PATCH и сразу меняет подписи', async () => {
    const fetchMock = stubFetch((request) =>
      request.method === 'PATCH'
        ? Response.json({ ...PROFILE, language: 'en' })
        : Response.json(PROFILE),
    )

    renderWithProviders(<Profile />)
    await screen.findByText('Аня')
    fireEvent.click(screen.getByRole('button', { name: 'English' }))

    expect(await screen.findByRole('heading', { name: 'Profile' })).toBeInTheDocument()
    const patched = fetchMock.mock.calls
      .map(([request]) => request as Request)
      .find((request) => request.method === 'PATCH')
    expect(patched).toBeDefined()
    expect(await patched?.json()).toEqual({ name: 'Аня', language: 'en' })
  })

  it('показывает согласие на новости и подсказку про сервисные сообщения', async () => {
    stubFetch((request) =>
      new URL(request.url).pathname === '/api/me/notifications'
        ? Response.json({ marketing_enabled: true })
        : Response.json(PROFILE),
    )

    renderWithProviders(<Profile />)

    const toggle = await screen.findByRole('switch', { name: 'Новости и предложения' })
    expect(toggle).toBeChecked()
    // Отписка не должна читаться как отказ от сообщений об оплате и подписке.
    expect(
      screen.getByText(
        'Сообщения об оплате, окончании подписки и ответах поддержки приходят всегда',
      ),
    ).toBeInTheDocument()
  })

  it('снятое согласие уезжает PATCH с marketing_enabled: false', async () => {
    const fetchMock = stubFetch((request) => {
      if (new URL(request.url).pathname !== '/api/me/notifications') return Response.json(PROFILE)
      return Response.json({ marketing_enabled: request.method !== 'PATCH' })
    })

    renderWithProviders(<Profile />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Новости и предложения' }))

    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Новости и предложения' })).not.toBeChecked(),
    )
    const patched = fetchMock.mock.calls
      .map(([request]) => request as Request)
      .find((request) => request.method === 'PATCH')
    expect(patched).toBeDefined()
    expect(await patched?.json()).toEqual({ marketing_enabled: false })
  })

  it('при ошибке загрузки предлагает повторить, а не показывает пустоту', async () => {
    withRussianLocale()
    const fetchMock = stubFetch(() =>
      Response.json({ error: { code: 'unauthorized' } }, { status: 500 }),
    )

    renderWithProviders(<Profile />)
    fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }))

    expect(screen.getByText('Что-то пошло не так')).toBeInTheDocument()
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(1))
  })
})
