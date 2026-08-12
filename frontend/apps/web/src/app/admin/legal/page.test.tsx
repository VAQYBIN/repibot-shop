import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminLegalPage from './page'

afterEach(() => vi.unstubAllGlobals())

function profile(role: string) {
  return {
    id: 1,
    email: 'admin@example.org',
    email_verified: true,
    telegram_username: null,
    name: null,
    language: 'ru',
    role,
    referral_code: 'ABC12345',
    has_password: true,
    has_telegram: false,
    passkey_count: 0,
  }
}

const LIST = [
  {
    slug: 'terms',
    locale: 'ru',
    title: 'Пользовательское соглашение',
    published_version: 1,
    published_at: '2026-08-01T00:00:00Z',
    withdrawn: false,
    has_draft: false,
  },
]

const DOCUMENT = {
  slug: 'terms',
  locale: 'ru',
  title: 'Пользовательское соглашение',
  content: '## Общие\n\nтекст',
  html: '<h2>Общие</h2>\n<p>текст</p>',
  version: 1,
  published_at: '2026-08-01T00:00:00Z',
}

const VERSIONS = [
  {
    version: 1,
    published_at: '2026-08-01T00:00:00Z',
    withdrawn_at: null,
    created_at: '2026-07-30T00:00:00Z',
  },
]

describe('админский экран юридических документов', () => {
  it('показывает пустое состояние, когда документов нет', async () => {
    renderWithProviders(<AdminLegalPage />, {
      handlers: { '/api/me': profile('admin'), '/api/admin/legal': [] },
    })

    expect(await screen.findByText(/пока нет/i)).toBeInTheDocument()
  })

  it('открывает документ и показывает предпросмотр', async () => {
    renderWithProviders(<AdminLegalPage />, {
      handlers: {
        '/api/me': profile('admin'),
        '/api/admin/legal': LIST,
        '/api/admin/legal/terms/ru': DOCUMENT,
        '/api/admin/legal/terms/ru/versions': VERSIONS,
      },
    })

    await userEvent.click(
      await screen.findByRole('button', { name: /Пользовательское соглашение/i }),
    )

    await userEvent.click(await screen.findByRole('tab', { name: /предпросмотр/i }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Общие' })).toBeInTheDocument())
  })

  it('подставляет загруженный с Telegra.ph текст в поля, не сохраняя его', async () => {
    const saves: Request[] = []
    renderWithProviders(<AdminLegalPage />, {
      handlers: {
        '/api/me': profile('admin'),
        '/api/admin/legal': LIST,
        '/api/admin/legal/terms/ru': (request: Request) => {
          if (request.method !== 'GET') saves.push(request)
          return DOCUMENT
        },
        '/api/admin/legal/terms/ru/versions': VERSIONS,
        '/api/admin/legal/import': { title: 'Политика', content: 'Текст политики.' },
      },
    })

    await userEvent.click(
      await screen.findByRole('button', { name: /Пользовательское соглашение/i }),
    )

    await userEvent.type(
      await screen.findByLabelText(/ссылка на telegra\.ph/i),
      'https://telegra.ph/Politika-06-01-36',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Загрузить' }))

    await waitFor(() => expect(screen.getByLabelText(/заголовок/i)).toHaveValue('Политика'))
    expect(saves).toHaveLength(0)
  })

  it('отказывает роли поддержки вместо показа редактора', async () => {
    renderWithProviders(<AdminLegalPage />, { handlers: { '/api/me': profile('support') } })

    expect(await screen.findByText(/только администратору/)).toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
  })
})
