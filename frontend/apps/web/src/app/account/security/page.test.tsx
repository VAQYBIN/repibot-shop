import { fireEvent, screen, waitFor, within } from '@testing-library/react'
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

const PASSKEYS = [
  { id: 7, name: 'Рабочий ноутбук', created_at: '2026-08-01T09:00:00Z', last_used_at: null },
]

/** Страница живёт сразу на трёх запросах, поэтому ответы разводятся по адресу. */
function stubApi(profile: Record<string, unknown> = PROFILE) {
  const fetchMock = vi.fn(async (request: Request) => {
    if (request.url.endsWith('/api/me')) return Response.json(profile)
    if (request.url.endsWith('/api/me/sessions')) return Response.json([])
    if (request.url.includes('/api/me/passkeys')) {
      if (request.method === 'DELETE') return new Response(null, { status: 204 })
      return Response.json(PASSKEYS)
    }
    if (request.url.endsWith('/api/me/email/change-request')) {
      return Response.json({ status: 'confirmation_sent' }, { status: 202 })
    }
    if (request.url.endsWith('/api/me/telegram/link-code')) {
      return Response.json({
        code: 'ABC123',
        url: 'https://t.me/repibot_bot?start=link_ABC123',
        expires_in: 600,
      })
    }
    if (request.url.endsWith('/api/me/telegram')) return new Response(null, { status: 204 })
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

const LINKED = { ...PROFILE, has_telegram: true, telegram_username: 'ivan' }

describe('привязка Telegram в разделе безопасности', () => {
  it('выдаёт код привязки и ссылку на бота', async () => {
    stubApi()
    renderWithAuth(<SecurityPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'Привязать Telegram' }))

    expect(await screen.findByText('ABC123')).toBeInTheDocument()
    // Ссылка, а не кнопка с window.open: адрес чужого домена должен быть
    // виден и открываться средствами браузера.
    expect(screen.getByRole('link', { name: 'Открыть бота' })).toHaveAttribute(
      'href',
      'https://t.me/repibot_bot?start=link_ABC123',
    )
  })

  it('привязанный аккаунт показан по @username', async () => {
    stubApi(LINKED)
    renderWithAuth(<SecurityPage />)

    expect(await screen.findByText('@ivan')).toBeInTheDocument()
  })

  it('отвязка сначала спрашивает подтверждение', async () => {
    const fetchMock = stubApi(LINKED)
    renderWithAuth(<SecurityPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'Отвязать' }))

    const dialog = await screen.findByRole('dialog', { name: 'Отвязать Telegram?' })
    // До подтверждения запроса нет: окно на то и окно, чтобы передумать.
    expect(fetchMock.mock.calls.some(([request]) => request.method === 'DELETE')).toBe(false)

    fireEvent.click(within(dialog).getByRole('button', { name: 'Отвязать' }))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([request]) => request.method === 'DELETE')).toBe(true)
    })
  })

  it('объясняет отказ снять последний способ входа', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.url.endsWith('/api/me')) return Response.json(LINKED)
        if (request.url.endsWith('/api/me/sessions')) return Response.json([])
        if (request.url.includes('/api/me/passkeys')) return Response.json([])
        return Response.json({ error: { code: 'last_login_method' } }, { status: 409 })
      }),
    )
    renderWithAuth(<SecurityPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'Отвязать' }))
    const dialog = await screen.findByRole('dialog', { name: 'Отвязать Telegram?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Отвязать' }))

    // Роль проверяется у самой фразы: на странице есть и другие карточки со
    // своими сообщениями, и getByRole('alert') нашёл бы их вместе с этим.
    // Alert из @repibot/ui кладёт текст во вложенный div, а role="alert" —
    // на внешний: проверяем ближайшего предка с этой ролью.
    const alert = await screen.findByText('Это единственный способ входа — сначала добавьте другой')
    expect(alert.closest('[role="alert"]')).not.toBeNull()
  })
})

describe('ключи доступа в разделе безопасности', () => {
  it('показывает заведённые ключи и предлагает добавить новый', async () => {
    stubApi()
    renderWithAuth(<SecurityPage />)

    expect(await screen.findByText('Рабочий ноутбук')).toBeInTheDocument()
    expect(await screen.findByText('Ещё не использовался')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Добавить ключ' })).toBeEnabled()
  })

  it('удаление ключа сначала спрашивает подтверждение', async () => {
    const fetchMock = stubApi()
    renderWithAuth(<SecurityPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'Удалить' }))

    const dialog = await screen.findByRole('dialog', { name: 'Удалить ключ?' })
    // До подтверждения запроса нет: окно на то и окно, чтобы передумать.
    expect(fetchMock.mock.calls.some(([request]) => request.method === 'DELETE')).toBe(false)

    fireEvent.click(within(dialog).getByRole('button', { name: 'Удалить' }))

    await waitFor(() => {
      const deleted = fetchMock.mock.calls.find(([request]) => request.method === 'DELETE')
      expect(deleted?.[0].url).toMatch(/\/api\/me\/passkeys\/7$/)
    })
  })

  it('объясняет отказ снять единственный ключ', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (request: Request) => {
        if (request.url.endsWith('/api/me')) return Response.json(PROFILE)
        if (request.url.endsWith('/api/me/sessions')) return Response.json([])
        if (request.method === 'DELETE') {
          return Response.json({ error: { code: 'last_login_method' } }, { status: 409 })
        }
        if (request.url.includes('/api/me/passkeys')) return Response.json(PASSKEYS)
        return new Response(null, { status: 404 })
      }),
    )
    renderWithAuth(<SecurityPage />)

    fireEvent.click(await screen.findByRole('button', { name: 'Удалить' }))
    const dialog = await screen.findByRole('dialog', { name: 'Удалить ключ?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Удалить' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Это единственный способ входа — сначала добавьте другой',
    )
  })
})
