import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithAuth } from '@/test/providers'
import LoginPage from './page'

// vi.mock поднимается выше импортов, поэтому мок роутера создаётся через
// vi.hoisted — иначе ссылка на replace окажется в мёртвой зоне.
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }))

afterEach(() => {
  vi.unstubAllGlobals()
  replace.mockReset()
})

describe('страница входа', () => {
  it('показывает ошибку формы до отправки запроса', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    renderWithAuth(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Почта'), { target: { value: 'не адрес' } })
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    // Заведомо неверные данные до сети не доходят.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('переводит код ошибки бэкенда во внятную фразу', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code: 'invalid_credentials' } }, { status: 401 })),
    )
    renderWithAuth(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Почта'), { target: { value: 'user@example.org' } })
    fireEvent.change(screen.getByLabelText('Пароль'), {
      target: { value: 'совершенно обычный пароль' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }))

    await waitFor(() => {
      // Пользователь видит фразу, а не код: код — контракт для фронтенда.
      expect(screen.getByRole('alert').textContent).not.toContain('invalid_credentials')
    })
    expect(screen.getByRole('alert')).toHaveTextContent('Неверная почта или пароль')
  })

  it('после успешного входа уводит в кабинет', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ access_token: 'jwt', expires_in: 900 })),
    )
    renderWithAuth(<LoginPage />)

    fireEvent.change(screen.getByLabelText('Почта'), { target: { value: 'user@example.org' } })
    fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'пароль подлиннее' } })
    fireEvent.click(screen.getByRole('button', { name: 'Войти' }))

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/account'))
  })

  it('вход через Telegram отключён до плана 1b', () => {
    renderWithAuth(<LoginPage />)

    expect(screen.getByRole('button', { name: /Telegram/ })).toBeDisabled()
  })
})
