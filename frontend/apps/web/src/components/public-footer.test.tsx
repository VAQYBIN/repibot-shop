import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PublicFooter } from './public-footer'

const useLegalDocuments = vi.fn()

vi.mock('@repibot/core', () => ({
  useLegalDocuments: (language: string) => useLegalDocuments(language),
  translate: (_: string, key: string) => key,
}))

vi.mock('@/lib/browser-preferences', () => ({
  useBrowserPreferences: () => ({ language: 'ru', theme: 'light', setTheme: vi.fn() }),
}))

describe('подвал публичных страниц', () => {
  it('показывает правовые ссылки, когда документы заведены', () => {
    useLegalDocuments.mockReturnValue({
      data: [
        { slug: 'terms', title: 'Пользовательское соглашение', published_at: '2026-08-01' },
        { slug: 'privacy', title: 'Политика конфиденциальности', published_at: '2026-08-01' },
      ],
      isPending: false,
      isError: false,
    })

    render(<PublicFooter />)

    expect(screen.getByRole('link', { name: 'Пользовательское соглашение' })).toHaveAttribute(
      'href',
      '/legal/terms',
    )
    expect(screen.getByRole('link', { name: 'Политика конфиденциальности' })).toHaveAttribute(
      'href',
      '/legal/privacy',
    )
  })

  it('не рисует раздел целиком, когда документов нет', () => {
    useLegalDocuments.mockReturnValue({ data: [], isPending: false, isError: false })

    render(<PublicFooter />)

    expect(screen.queryByText('footer.legal')).not.toBeInTheDocument()
  })

  it('молчит и при неудачном запросе', () => {
    useLegalDocuments.mockReturnValue({ data: undefined, isPending: false, isError: true })

    render(<PublicFooter />)

    expect(screen.queryByText('footer.legal')).not.toBeInTheDocument()
    // Остальной подвал при этом на месте: недоступный API не должен уносить навигацию.
    // Подписи здесь — ключи: translate в моке возвращает ключ, а не перевод.
    expect(screen.getByRole('link', { name: 'nav.plans' })).toBeInTheDocument()
  })
})
