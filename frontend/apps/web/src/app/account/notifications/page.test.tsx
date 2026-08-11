import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import NotificationsPage from './page'

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

function patchedBody(): Promise<unknown> | undefined {
  const mock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>
  const call = mock.mock.calls.find(([request]) => (request as Request).method === 'PATCH')
  return (call?.[0] as Request | undefined)?.json()
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('уведомления в кабинете', () => {
  it('показывает включённое согласие и подсказку про сервисные сообщения', async () => {
    renderWithProviders(<NotificationsPage />, {
      handlers: {
        '/api/me': PROFILE,
        '/api/me/notifications': { marketing_enabled: true },
      },
    })

    const toggle = await screen.findByRole('switch', { name: 'Новости и предложения' })
    expect(toggle).toBeChecked()
    // Человек должен видеть, что оплата и окончание подписки придут в любом случае.
    expect(
      screen.getByText(
        'Сообщения об оплате, окончании подписки и ответах поддержки приходят всегда',
      ),
    ).toBeInTheDocument()
  })

  it('снятый переключатель уезжает PATCH с marketing_enabled: false', async () => {
    renderWithProviders(<NotificationsPage />, {
      handlers: {
        '/api/me': PROFILE,
        // Тип Handler в обёртке — объединение с unknown, и ветка с функцией в
        // нём стирается: параметр приходится называть здесь.
        '/api/me/notifications': (request: Request) =>
          request.method === 'PATCH' ? { marketing_enabled: false } : { marketing_enabled: true },
      },
    })

    fireEvent.click(await screen.findByRole('switch', { name: 'Новости и предложения' }))

    await waitFor(async () => {
      await expect(patchedBody()).resolves.toEqual({ marketing_enabled: false })
    })
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: 'Новости и предложения' })).not.toBeChecked(),
    )
  })
})
