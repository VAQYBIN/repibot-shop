import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthState } from '../auth'
import { PROFILE, renderWithProviders, stubFetch, withRussianLocale } from '../test-utils'
import { Home } from './index'

// Состояние входа сбрасывается до отрисовки: после неё React уже смонтирован,
// и обновление хранилища мимо act() дало бы предупреждение.
beforeEach(() => {
  useAuthState.setState({ state: 'checking' })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('главная MiniApp', () => {
  it('пока идёт вход, показывает скелет, а не пустой экран', () => {
    withRussianLocale()

    renderWithProviders(<Home />)

    expect(screen.getByText('Загрузка')).toBeInTheDocument()
  })

  it('вне Telegram предлагает открыть приложение через бота', () => {
    withRussianLocale()
    useAuthState.setState({ state: 'outside' })

    renderWithProviders(<Home />)

    expect(screen.getByText('Откройте приложение через бота Re:Pibot')).toBeInTheDocument()
  })

  it('после неудачного входа даёт повторить попытку', () => {
    withRussianLocale()
    const signIn = vi.fn(async () => {})
    useAuthState.setState({ state: 'failed', signIn })

    renderWithProviders(<Home />)
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))

    expect(screen.getByText('Не удалось войти')).toBeInTheDocument()
    expect(signIn).toHaveBeenCalledTimes(1)
  })

  it('после входа здоровается именем из профиля', async () => {
    stubFetch(() => Response.json(PROFILE))
    useAuthState.setState({ state: 'ready' })

    renderWithProviders(<Home />)

    expect(
      await screen.findByRole('heading', { name: 'Добро пожаловать, Аня' }),
    ).toBeInTheDocument()
  })

  it('говорит на языке из профиля, а не из настроек браузера', async () => {
    withRussianLocale()
    stubFetch(() => Response.json({ ...PROFILE, language: 'en' }))
    useAuthState.setState({ state: 'ready' })

    renderWithProviders(<Home />)

    expect(await screen.findByText('The shop is still being built')).toBeInTheDocument()
  })

  it('ошибку профиля показывает с кнопкой повтора', async () => {
    withRussianLocale()
    stubFetch(() => Response.json({ error: { code: 'unauthorized' } }, { status: 500 }))
    useAuthState.setState({ state: 'ready' })

    renderWithProviders(<Home />)

    expect(await screen.findByText('Что-то пошло не так')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument()
  })
})
