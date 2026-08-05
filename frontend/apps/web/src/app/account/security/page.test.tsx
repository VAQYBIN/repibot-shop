import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithAuth } from '@/test/providers'
import SecurityPage from './page'

const PROFILE = {
  user_id: 1,
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

/** Страница живёт сразу на трёх запросах, поэтому ответы разводятся по адресу. */
function stubApi(profile: Record<string, unknown> = PROFILE) {
  const fetchMock = vi.fn(async (request: Request) => {
    if (request.url.endsWith('/api/me')) return Response.json(profile)
    if (request.url.endsWith('/api/me/sessions')) return Response.json([])
    if (request.url.endsWith('/api/me/email/change-request')) {
      return Response.json({ status: 'confirmation_sent' }, { status: 202 })
    }
    return new Response(null, { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function sentTo(fetchMock: ReturnType<typeof stubApi>): Request | undefined {
  const call = fetchMock.mock.calls.find(([request]) =>
    (request as Request).url.endsWith('/api/me/email/change-request'),
  )
  return call?.[0] as Request | undefined
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('смена почты в разделе безопасности', () => {
  it('заведомо неверный адрес объясняется у поля и до сети не доходит', async () => {
    const fetchMock = stubApi()
    renderWithAuth(<SecurityPage />)

    const field = await screen.findByLabelText('Новая почта')
    fireEvent.change(field, { target: { value: 'не адрес' } })
    fireEvent.click(screen.getByRole('button', { name: 'Отправить письмо' }))

    // Причина отказа читается скринридером вместе с полем, а не отдельно.
    await waitFor(() => {
      expect(field).toHaveAccessibleDescription(/Похоже, это не адрес почты/)
    })
    expect(field).toBeInvalid()
    expect(sentTo(fetchMock)).toBeUndefined()
  })

  it('после успеха сообщает, что письмо ушло на новый адрес', async () => {
    const fetchMock = stubApi()
    renderWithAuth(<SecurityPage />)

    fireEvent.change(await screen.findByLabelText('Новая почта'), {
      target: { value: 'new@example.org' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Отправить письмо' }))

    expect(await screen.findByText('Письмо отправлено на новый адрес')).toBeInTheDocument()
    const request = sentTo(fetchMock)
    expect(request).toBeDefined()
    expect(await request?.json()).toEqual({ email: 'new@example.org' })
  })

  it('переводит код ошибки бэкенда во внятную фразу', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.url.endsWith('/api/me')) return Response.json(PROFILE)
        if (request.url.endsWith('/api/me/sessions')) return Response.json([])
        return Response.json({ error: { code: 'email_taken' } }, { status: 409 })
      }),
    )
    renderWithAuth(<SecurityPage />)

    fireEvent.change(await screen.findByLabelText('Новая почта'), {
      target: { value: 'taken@example.org' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Отправить письмо' }))

    expect(await screen.findByText('Этот адрес уже занят')).toBeInTheDocument()
  })

  it('аккаунту без почты та же форма предлагает её добавить', async () => {
    stubApi({
      ...PROFILE,
      email: null,
      email_verified: false,
      has_password: false,
      has_telegram: true,
    })
    renderWithAuth(<SecurityPage />)

    expect(await screen.findByRole('heading', { name: 'Добавление почты' })).toBeInTheDocument()
    expect(screen.getByLabelText('Почта')).toBeInTheDocument()
  })
})
