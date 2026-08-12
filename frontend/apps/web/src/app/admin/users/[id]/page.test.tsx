import { act, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Suspense } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminUserCardPage from './page'

afterEach(() => vi.unstubAllGlobals())

type Handlers = NonNullable<Parameters<typeof renderWithProviders>[1]>['handlers']

function makeCard() {
  return {
    row: {
      id: 42,
      name: 'Вася',
      email: 'vasya@example.com',
      telegram_id: 700_001,
      telegram_username: 'vasya',
      plan_name: 'Год',
      subscription_status: 'active',
      expires_at: '2026-12-01T00:00:00.000Z',
      banned: false,
      support_muted: false,
    },
    language: 'ru',
    role: 'user',
    created_at: '2026-01-01T00:00:00.000Z',
    email_verified: true,
    referred_by_id: null,
    subscription_source: 'purchase',
    auto_renew: true,
    subscription_url: 'https://panel.example/sub/old',
    remnawave_id: 15,
  }
}

function entry(at: string, title: string) {
  return { at, kind: 'staff', title, detail: null, actor: 'admin@example.com' }
}

const devices = {
  devices: [
    {
      hwid: 'HW-1',
      platform: 'iOS',
      device_model: 'iPhone 14',
      os_version: '17.4',
      created_at: '2026-05-01T00:00:00.000Z',
    },
  ],
  limit: 3,
  used: 1,
}

const panelSilent = {
  status: 503,
  body: { error: { code: 'panel_unavailable', message: 'панель недоступна' } },
}

/**
 * Страница получает номер человека тем же путём, что и в приложении, —
 * обещанием `params`. Отсюда две особенности: граница `Suspense`, потому что
 * `use` ждёт обещание, и пустой `act` следом — без него React так и остаётся
 * на приостановленной отрисовке, а тест видит пустую страницу.
 */
async function show(role: string, handlers: Handlers): Promise<void> {
  await act(async () => {
    renderWithProviders(
      <Suspense fallback={null}>
        <AdminUserCardPage params={Promise.resolve({ id: '42' })} />
      </Suspense>,
      { handlers: { '/api/me': { id: 1, role }, ...handlers } },
    )
  })
}

/**
 * Действия карточки собраны в выпадающее меню рядом с именем: пункт нельзя
 * нажать, пока меню не открыто.
 */
async function openActions(): Promise<void> {
  await userEvent.click(await screen.findByRole('button', { name: 'Действия' }))
}

function baseHandlers(card: unknown = makeCard()): Handlers {
  return {
    '/api/admin/users/42': card,
    '/api/admin/users/42/journal': [entry('2026-08-01T09:00:00.000Z', 'Продление подписки')],
    '/api/admin/users/42/devices': devices,
    '/api/admin/plans': [{ id: 1, code: 'year', name: { ru: 'Год' } }],
  }
}

describe('карточка пользователя в админке', () => {
  it('не показывает поддержке кнопки про дни и тариф', async () => {
    // Отказ сервера — последняя линия, а не первая: кнопка, которая всегда
    // отвечает «нельзя», хуже отсутствующей.
    const requests: string[] = []
    await show('support', {
      ...baseHandlers(),
      '/api/admin/plans': (request: Request) => {
        requests.push(request.url)
        return []
      },
    })

    expect(await screen.findByText('vasya@example.com')).toBeInTheDocument()
    await openActions()
    expect(screen.getByRole('menuitem', { name: 'Заблокировать' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Выдать дни' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Сменить тариф' })).not.toBeInTheDocument()
    // Тарифы поддержке даже не запрашиваются: они нужны только форме, которой у
    // неё нет.
    expect(requests).toHaveLength(0)
  })

  it('даёт администратору выдать дни и сменить тариф', async () => {
    await show('admin', baseHandlers())

    expect(await screen.findByRole('button', { name: 'Выдать дни' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сменить тариф' })).toBeInTheDocument()
  })

  it('спрашивает подтверждение перед блокировкой и перечитывает карточку с журналом', async () => {
    const card = makeCard()
    const journal = [entry('2026-08-01T09:00:00.000Z', 'Продление подписки')]
    const blocks: Request[] = []
    await show('support', {
      ...baseHandlers(card),
      '/api/admin/users/42/journal': () => journal,
      '/api/admin/users/42/block': (request: Request) => {
        blocks.push(request)
        card.row.banned = true
        journal.unshift(entry('2026-08-12T09:00:00.000Z', 'Блокировка'))
        return { changed: true }
      },
    })

    await screen.findByText('vasya@example.com')
    await openActions()
    await userEvent.click(screen.getByRole('menuitem', { name: 'Заблокировать' }))

    // Окно открылось, но запроса ещё нет: подтверждение только тогда и имеет
    // смысл, когда до него ничего не случилось.
    const dialog = await screen.findByRole('dialog')
    expect(blocks).toHaveLength(0)

    await userEvent.click(within(dialog).getByRole('button', { name: 'Да, заблокировать' }))

    expect(blocks).toHaveLength(1)
    // Пункт меню сменился на противоположный: состояние действительно
    // обновилось, а не просто закрылось окно подтверждения.
    await openActions()
    expect(screen.getByRole('menuitem', { name: 'Разблокировать' })).toBeInTheDocument()
    expect(blocks[0]?.method).toBe('POST')
    // Решение персонала — событие ленты: не показать его сразу значит заставить
    // сотрудника обновлять страницу.
    expect(await screen.findByText('Блокировка')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('отменённое подтверждение ничего не делает', async () => {
    const blocks: Request[] = []
    await show('support', {
      ...baseHandlers(),
      '/api/admin/users/42/block': (request: Request) => {
        blocks.push(request)
        return { changed: true }
      },
    })

    await openActions()
    await userEvent.click(screen.getByRole('menuitem', { name: 'Заблокировать' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(blocks).toHaveLength(0)
  })

  it('спрашивает подтверждение перед новой ссылкой подписки', async () => {
    const card = makeCard()
    const revokes: Request[] = []
    await show('support', {
      ...baseHandlers(card),
      '/api/admin/users/42/subscription/revoke-link': (request: Request) => {
        revokes.push(request)
        card.subscription_url = 'https://panel.example/sub/new'
        return { subscription_url: 'https://panel.example/sub/new', short_uuid: 'new' }
      },
    })

    await openActions()
    await userEvent.click(screen.getByRole('menuitem', { name: 'Выпустить новую ссылку' }))
    const dialog = await screen.findByRole('dialog')
    expect(revokes).toHaveLength(0)

    await userEvent.click(within(dialog).getByRole('button', { name: 'Да, выпустить' }))

    expect(revokes).toHaveLength(1)
    expect(await screen.findByText('https://panel.example/sub/new')).toBeInTheDocument()
  })

  it('читает «changed: false» как чужое опережение, а не как успех', async () => {
    await show('support', {
      ...baseHandlers(),
      '/api/admin/users/42/mute': { changed: false },
    })

    await openActions()
    await userEvent.click(screen.getByRole('menuitem', { name: 'Закрыть поддержку' }))

    expect(await screen.findByText(/коллега успел раньше/)).toBeInTheDocument()
  })

  it('молчащая панель гасит только устройства', async () => {
    // Устройства просит отдельный маршрут именно поэтому: карточка обязана
    // открыться и тогда, когда панель молчит.
    let silent = true
    await show('support', {
      ...baseHandlers(),
      '/api/admin/users/42/devices': () => (silent ? panelSilent : devices),
    })

    expect(await screen.findByText('vasya@example.com')).toBeInTheDocument()
    expect(await screen.findByText(/Панель не отвечает/)).toBeInTheDocument()

    silent = false
    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }))

    expect(await screen.findByText('iPhone 14')).toBeInTheDocument()
    expect(screen.queryByText(/Панель не отвечает/)).not.toBeInTheDocument()
  })

  it('отвязывает устройство и перечитывает список', async () => {
    const unlinks: Request[] = []
    const shown = { devices: [...devices.devices], limit: 3, used: 1 }
    await show('support', {
      ...baseHandlers(),
      '/api/admin/users/42/devices': () => shown,
      '/api/admin/users/42/devices/HW-1': (request: Request) => {
        unlinks.push(request)
        shown.devices = []
        shown.used = 0
        return { status: 204, body: undefined }
      },
    })

    await userEvent.click(await screen.findByRole('button', { name: 'Отвязать iPhone 14' }))

    expect(unlinks).toHaveLength(1)
    expect(unlinks[0]?.method).toBe('DELETE')
    expect(await screen.findByText('Устройств нет')).toBeInTheDocument()
  })
})
