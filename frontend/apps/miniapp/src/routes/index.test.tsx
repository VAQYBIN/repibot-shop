import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Home } from './index'

afterEach(() => {
  vi.unstubAllGlobals()
})

/** По умолчанию jsdom сообщает en-US, а тексты проверяются по-русски. */
function withRussianLocale(): void {
  vi.stubGlobal('navigator', { ...navigator, languages: ['ru-RU'] })
}

describe('главная MiniApp', () => {
  it('показывает название и подзаголовок', () => {
    withRussianLocale()

    render(<Home />)

    expect(screen.getByRole('heading', { name: 'Re:Pibot' })).toBeInTheDocument()
    expect(screen.getByText('Магазин ещё готовится')).toBeInTheDocument()
  })

  it('сообщает, что открыт вне Telegram, когда SDK недоступен', () => {
    render(<Home />)

    expect(screen.getByText('Telegram: вне приложения')).toBeInTheDocument()
  })

  it('сообщает о подключении, когда initData получен', () => {
    vi.stubGlobal('Telegram', { WebApp: { initData: 'query_id=AAA' } })

    render(<Home />)

    expect(screen.getByText('Telegram: подключён')).toBeInTheDocument()
  })

  it('берёт язык, который Telegram выставил пользователю', () => {
    /* Определение языка написано и покрыто тестами в @repibot/core, но пока
       оно не подключено, интерфейс остаётся русским для всех. */
    vi.stubGlobal('Telegram', {
      WebApp: { initData: 'query_id=AAA', initDataUnsafe: { user: { language_code: 'en-US' } } },
    })

    render(<Home />)

    expect(screen.getByText('The shop is still being built')).toBeInTheDocument()
  })

  it('вне Telegram берёт язык из настроек браузера', () => {
    vi.stubGlobal('navigator', { ...navigator, languages: ['en-GB', 'ru'] })

    render(<Home />)

    expect(screen.getByText('The shop is still being built')).toBeInTheDocument()
  })

  it('падает обратно на русский, когда язык не поддержан', () => {
    vi.stubGlobal('navigator', { ...navigator, languages: ['de-DE', 'fr'] })

    render(<Home />)

    expect(screen.getByText('Магазин ещё готовится')).toBeInTheDocument()
  })
})
