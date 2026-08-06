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
