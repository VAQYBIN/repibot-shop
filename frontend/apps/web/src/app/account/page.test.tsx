import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AccountPage from './page'

const PROFILE = {
  id: 1,
  email: 'user@example.org',
  email_verified: true,
  telegram_username: null,
  name: null,
  language: 'ru',
  role: 'user',
  referral_code: 'ABC12345',
  has_password: true,
  has_telegram: false,
  passkey_count: 0,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('профиль в кабинете', () => {
  it('язык выбирается нативным списком', async () => {
    renderWithProviders(<AccountPage />, {
      handlers: { '/api/me': PROFILE },
    })

    const select = await screen.findByRole('combobox', { name: /язык|language/i })
    await userEvent.selectOptions(select, 'en')

    expect(select).toHaveValue('en')
  })
})
