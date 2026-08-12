import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LegalConsent } from './legal-consent'

const useLegalDocuments = vi.fn()

vi.mock('@repibot/core', () => ({
  useLegalDocuments: (language: string) => useLegalDocuments(language),
  translate: (_: string, key: string) => key,
}))

vi.mock('@/lib/browser-preferences', () => ({
  useBrowserPreferences: () => ({ language: 'ru', theme: 'light', setTheme: vi.fn() }),
}))

describe('согласие с документами', () => {
  it('перечисляет заведённые документы ссылками', () => {
    useLegalDocuments.mockReturnValue({
      data: [
        { slug: 'terms', title: 'Пользовательским соглашением', published_at: '2026-08-01' },
        { slug: 'privacy', title: 'Политикой конфиденциальности', published_at: '2026-08-01' },
      ],
      isPending: false,
      isError: false,
    })

    render(<LegalConsent />)

    expect(screen.getByRole('link', { name: 'Пользовательским соглашением' })).toHaveAttribute(
      'href',
      '/legal/terms',
    )
    expect(screen.getByRole('link', { name: 'Политикой конфиденциальности' })).toBeInTheDocument()
  })

  it('молчит, когда документов нет', () => {
    useLegalDocuments.mockReturnValue({ data: [], isPending: false, isError: false })

    const { container } = render(<LegalConsent />)

    expect(container).toBeEmptyDOMElement()
  })
})
