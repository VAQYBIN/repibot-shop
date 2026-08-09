import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders } from '@/test/providers'
import AdminPaymentsPage from './page'

afterEach(() => vi.unstubAllGlobals())

describe('админские корректировки оплаты', () => {
  it('marks a completed refund without sending a compensation', async () => {
    const requests: Request[] = []
    renderWithProviders(<AdminPaymentsPage />, {
      handlers: {
        '/api/admin/orders/41/refund-mark': (request: Request) => {
          requests.push(request)
          return { status: 204, body: undefined }
        },
      },
    })

    await userEvent.type(screen.getByLabelText('Номер заказа'), '41')
    await userEvent.type(screen.getByLabelText('Номер возврата провайдера'), 'refund_41')
    await userEvent.type(
      screen.getByLabelText('Причина отметки возврата'),
      'Возврат выполнен в YooKassa',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Отметить возврат' }))

    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    await expect(requests[0]?.json()).resolves.toEqual({
      reference: 'refund_41',
      comment: 'Возврат выполнен в YooKassa',
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(await screen.findByRole('status')).toHaveTextContent('Отметка возврата сохранена')
  })

  it('requires an explicit dialog confirmation before sending compensation', async () => {
    const requests: Request[] = []
    renderWithProviders(<AdminPaymentsPage />, {
      handlers: {
        '/api/admin/orders/41/compensations': (request: Request) => {
          requests.push(request)
          return { status: 204, body: undefined }
        },
      },
    })

    await userEvent.type(screen.getByLabelText('Номер заказа'), '41')
    await userEvent.selectOptions(screen.getByLabelText('Действие компенсации'), 'revoke_days')
    await userEvent.type(
      screen.getByLabelText('Причина компенсации'),
      'Подтверждённая отдельная корректировка',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Подготовить компенсацию' }))

    const dialog = await screen.findByRole('dialog', { name: 'Подтвердить компенсацию?' })
    expect(requests).toHaveLength(0)
    expect(dialog).toHaveTextContent('Срок подписки будет уменьшен на дни заказа.')

    await userEvent.click(within(dialog).getByRole('button', { name: 'Подтвердить компенсацию' }))

    expect(requests).toHaveLength(1)
    await expect(requests[0]?.json()).resolves.toMatchObject({
      action: 'revoke_days',
      comment: 'Подтверждённая отдельная корректировка',
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Компенсация применена')
  })
})
