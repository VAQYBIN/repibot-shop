'use client'

import { useAuthClient } from '@repibot/core'
import { Button, Card, Dialog, Input } from '@repibot/ui'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

type CompensationAction = 'revoke_days' | 'reverse_referral_reward'

function actionCopy(action: CompensationAction): string {
  return action === 'revoke_days'
    ? 'Срок подписки будет уменьшен на дни заказа.'
    : 'Реферальная награда за этот заказ будет сторнирована.'
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Операция не выполнена. Проверьте данные и права.'
}

export default function AdminPaymentsPage() {
  const { api } = useAuthClient()
  const [orderId, setOrderId] = useState('')
  const [reference, setReference] = useState('')
  const [refundComment, setRefundComment] = useState('')
  const [compensationAction, setCompensationAction] = useState<CompensationAction>('revoke_days')
  const [compensationComment, setCompensationComment] = useState('')
  const [confirmationOpen, setConfirmationOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const numericOrderId = Number(orderId)
  const hasOrderId = Number.isSafeInteger(numericOrderId) && numericOrderId > 0

  const refund = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST('/api/admin/orders/{order_id}/refund-mark', {
        params: { path: { order_id: numericOrderId } },
        body: { reference, comment: refundComment },
      })
      if (error) throw new Error('Не удалось сохранить отметку возврата.')
    },
    onSuccess: () => setNotice('Отметка возврата сохранена. Срок подписки не изменён.'),
  })

  const compensation = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST('/api/admin/orders/{order_id}/compensations', {
        params: { path: { order_id: numericOrderId } },
        body: {
          action: compensationAction,
          idempotency_key: crypto.randomUUID(),
          comment: compensationComment,
        },
      })
      if (error) throw new Error('Не удалось применить компенсацию.')
    },
    onSuccess: () => {
      setConfirmationOpen(false)
      setNotice('Компенсация применена.')
    },
  })

  const refundReady = hasOrderId && reference.trim() !== '' && refundComment.trim() !== ''
  const compensationReady = hasOrderId && compensationComment.trim() !== ''

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6 text-text">
      <header>
        <h1 className="text-2xl font-semibold">Платежи и корректировки</h1>
        <p className="mt-1 max-w-prose text-sm text-text-secondary">
          Сначала завершите возврат у провайдера. Локальная отметка не меняет срок подписки;
          компенсация всегда выполняется отдельно.
        </p>
      </header>

      <Card>
        <label htmlFor="order-id" className="text-sm font-medium text-text">
          Номер заказа
        </label>
        <Input
          id="order-id"
          type="number"
          min="1"
          inputMode="numeric"
          value={orderId}
          onChange={(event) => setOrderId(event.target.value)}
          className="mt-2 max-w-xs"
        />
      </Card>

      <section aria-labelledby="refund-heading">
        <Card>
          <h2 id="refund-heading" className="text-lg font-semibold text-text">
            Отметить выполненный возврат
          </h2>
          <p className="mt-1 text-sm text-text-secondary">
            Только после возврата в YooKassa или другом платёжном провайдере.
          </p>
          <div className="mt-4 grid gap-3">
            <div>
              <label htmlFor="refund-reference" className="text-sm font-medium text-text">
                Номер возврата провайдера
              </label>
              <Input
                id="refund-reference"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
                className="mt-2"
              />
            </div>
            <div>
              <label htmlFor="refund-comment" className="text-sm font-medium text-text">
                Причина отметки возврата
              </label>
              <Input
                id="refund-comment"
                value={refundComment}
                onChange={(event) => setRefundComment(event.target.value)}
                className="mt-2"
              />
            </div>
          </div>
          {refund.error === null ? null : (
            <p role="alert" className="mt-3 text-sm text-danger">
              {errorMessage(refund.error)}
            </p>
          )}
          <Button
            className="mt-4"
            disabled={!refundReady || refund.isPending}
            onClick={() => void refund.mutateAsync()}
          >
            Отметить возврат
          </Button>
        </Card>
      </section>

      <section aria-labelledby="compensation-heading">
        <Card>
          <h2 id="compensation-heading" className="text-lg font-semibold text-text">
            Отдельная компенсация
          </h2>
          <p className="mt-1 text-sm text-text-secondary">
            Необратимое действие. Его нельзя выполнить отметкой возврата и оно требует отдельного
            подтверждения.
          </p>
          <div className="mt-4 grid gap-3">
            <div>
              <label htmlFor="compensation-action" className="text-sm font-medium text-text">
                Действие компенсации
              </label>
              <select
                id="compensation-action"
                value={compensationAction}
                onChange={(event) =>
                  setCompensationAction(event.target.value as CompensationAction)
                }
                className="mt-2 h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-text focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none"
              >
                <option value="revoke_days">Списать дни подписки</option>
                <option value="reverse_referral_reward">Сторнировать реферальную награду</option>
              </select>
            </div>
            <div>
              <label htmlFor="compensation-comment" className="text-sm font-medium text-text">
                Причина компенсации
              </label>
              <Input
                id="compensation-comment"
                value={compensationComment}
                onChange={(event) => setCompensationComment(event.target.value)}
                className="mt-2"
              />
            </div>
          </div>
          {compensation.error === null ? null : (
            <p role="alert" className="mt-3 text-sm text-danger">
              {errorMessage(compensation.error)}
            </p>
          )}
          <Button
            variant="secondary"
            className="mt-4"
            disabled={!compensationReady || compensation.isPending}
            onClick={() => setConfirmationOpen(true)}
          >
            Подготовить компенсацию
          </Button>
        </Card>
      </section>

      {notice === null ? null : (
        <p role="status" className="text-sm text-text-accent">
          {notice}
        </p>
      )}

      <Dialog
        open={confirmationOpen}
        onClose={() => setConfirmationOpen(false)}
        title="Подтвердить компенсацию?"
        description={actionCopy(compensationAction)}
      >
        <Button variant="secondary" onClick={() => setConfirmationOpen(false)}>
          Отмена
        </Button>
        <Button disabled={compensation.isPending} onClick={() => void compensation.mutateAsync()}>
          Подтвердить компенсацию
        </Button>
      </Dialog>
    </main>
  )
}
