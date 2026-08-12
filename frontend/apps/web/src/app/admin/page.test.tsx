import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminPage from './page'

// vi.mock поднимается выше импортов, поэтому мок роутера создаётся через
// vi.hoisted — иначе ссылка на replace окажется в мёртвой зоне.
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }))

afterEach(() => {
  replace.mockClear()
  vi.unstubAllGlobals()
})

const metrics = {
  revenue_rub: '1234567.89',
  payments: 12,
  new_subscriptions: 5,
  renewals: 7,
  active_subscriptions: 340,
  tickets_waiting: 3,
}

type MetricsHandler = (request: Request) => unknown

function show(role: string, handler?: MetricsHandler) {
  return renderWithProviders(<AdminPage />, {
    handlers: {
      '/api/me': { id: 1, role },
      ...(handler === undefined ? {} : { '/api/admin/metrics': handler }),
    },
  })
}

describe('главная админки', () => {
  it('уводит поддержку к пользователям', async () => {
    // Сотруднику поддержки сводка не положена, а пустая главная выглядела бы
    // поломкой: он попадает туда, ради чего и открыл админку.
    show('support')

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/admin/users'))
  })

  it('перечитывает числа при смене периода', async () => {
    // Иначе переключатель врёт: подпись сменилась, числа прежние.
    const periods: (string | null)[] = []
    show('admin', (request) => {
      const period = new URL(request.url).searchParams.get('period')
      periods.push(period)
      return period === 'month' ? { ...metrics, payments: 40 } : metrics
    })

    expect(await screen.findByText('12')).toBeInTheDocument()
    // Период стал вкладкой, а не кнопкой — вид сменился, значения и обработчик те же.
    await userEvent.click(screen.getByRole('tab', { name: '30 дней' }))

    expect(await screen.findByText('40')).toBeInTheDocument()
    expect(periods).toEqual(['today', 'month'])
  })

  it('выводит выручку разрядами и рублями', async () => {
    // Копейки приходят строкой и обязаны дойти до экрана без потерь: сумма
    // выручки — это то, по чему владелец судит о дне.
    show('admin', () => metrics)

    // Разряды на экране разделены неразрывным пробелом, а поиск по тексту
    // сводит любые пробелы к одному — отсюда \s в образце.
    expect(await screen.findByText(/^1\s234\s567,89\s₽$/)).toBeInTheDocument()
  })

  it('подписывает плитки состояния как «сейчас»', async () => {
    // Без подписи «активные подписки за сегодня» читается как «появившиеся
    // сегодня»: эти две плитки не зависят от выбранного периода.
    show('admin', () => metrics)

    const active = await screen.findByRole('group', { name: 'Активные подписки' })
    expect(within(active).getByText(/Сейчас/)).toBeInTheDocument()

    const waiting = screen.getByRole('group', { name: 'Ждут ответа' })
    expect(within(waiting).getByText(/Сейчас/)).toBeInTheDocument()

    const payments = screen.getByRole('group', { name: 'Оплаты' })
    expect(within(payments).queryByText(/Сейчас/)).not.toBeInTheDocument()
  })

  it('ведёт с плитки ожидающих обращений к обращениям', async () => {
    // Число ждущих ответа — повод открыть их прямо сейчас, а не искать раздел
    // в меню.
    show('admin', () => metrics)

    const link = await screen.findByRole('link', { name: /Ждут ответа/ })
    expect(link).toHaveAttribute('href', '/admin/tickets')
  })

  it('показывает загрузку, а не нули, пока числа не пришли', async () => {
    // Ноль выручки и неизвестная выручка выглядят одинаково, но значат разное:
    // вместо текста на время загрузки теперь шесть плиток-заглушек, чтобы
    // сетка не прыгала, когда числа придут.
    const { container } = show('admin', () => new Promise(() => undefined))

    await waitFor(() => {
      expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(6)
    })
    expect(screen.queryByText(/₽/)).not.toBeInTheDocument()
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
  })
})
