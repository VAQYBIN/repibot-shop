import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PublicHeader } from './public-header'

vi.mock('@/lib/browser-preferences', () => ({
  useBrowserPreferences: () => ({ language: 'ru', theme: 'light', setTheme: vi.fn() }),
}))

describe('шапка публичных страниц', () => {
  it('ведёт на главную, тарифы и вход', () => {
    render(<PublicHeader />)

    expect(screen.getByRole('link', { name: /на главную/i })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Тарифы' })).toHaveAttribute('href', '/plans')
    expect(screen.getByRole('link', { name: 'Войти' })).toHaveAttribute('href', '/login')
  })

  it('даёт сменить тему до входа', () => {
    render(<PublicHeader />)

    expect(screen.getByRole('button', { name: /тема/i })).toBeInTheDocument()
  })
})
