'use client'

import { useAuthClient } from '@repibot/core'
import { Alert, Button, Card, Dialog, FormField, Input, Select } from '@repibot/ui'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

import { AdminPage } from '@/components/admin-page'

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
    <AdminPage
      title="Платежи и корректировки"
      description="Сначала завершите возврат у провайдера. Локальная отметка не меняет срок подписки; компенсация всегда выполняется отдельно."
    >
      <Card>
        <FormField label="Номер заказа" htmlFor="order-id">
          <Input
            id="order-id"
            type="number"
            min="1"
            inputMode="numeric"
            value={orderId}
            onChange={(event) => setOrderId(event.target.value)}
            className="max-w-xs"
          />
        </FormField>
      </Card>

      <section aria-labelledby="refund-heading">
        <Card>
          <h2 id="refund-heading" className="font-medium text-h3 text-text">
            Отметить выполненный возврат
          </h2>
          <p className="mt-1 text-small text-text-secondary">
            Только после возврата в YooKassa или другом платёжном провайдере.
          </p>
          <div className="mt-4 grid gap-3">
            <FormField label="Номер возврата провайдера" htmlFor="refund-reference">
              <Input
                id="refund-reference"
                value={reference}
                onChange={(event) => setReference(event.target.value)}
              />
            </FormField>
            <FormField label="Причина отметки возврата" htmlFor="refund-comment">
              <Input
                id="refund-comment"
                value={refundComment}
                onChange={(event) => setRefundComment(event.target.value)}
              />
            </FormField>
          </div>
          {refund.error === null ? null : (
            <Alert tone="error" className="mt-3">
              {errorMessage(refund.error)}
            </Alert>
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
          <h2 id="compensation-heading" className="font-medium text-h3 text-text">
            Отдельная компенсация
          </h2>
          <p className="mt-1 text-small text-text-secondary">
            Необратимое действие. Его нельзя выполнить отметкой возврата и оно требует отдельного
            подтверждения.
          </p>
          <div className="mt-4 grid gap-3">
            <FormField label="Действие компенсации" htmlFor="compensation-action">
              <Select
                id="compensation-action"
                value={compensationAction}
                onChange={(event) =>
                  setCompensationAction(event.target.value as CompensationAction)
                }
              >
                <option value="revoke_days">Списать дни подписки</option>
                <option value="reverse_referral_reward">Сторнировать реферальную награду</option>
              </Select>
            </FormField>
            <FormField label="Причина компенсации" htmlFor="compensation-comment">
              <Input
                id="compensation-comment"
                value={compensationComment}
                onChange={(event) => setCompensationComment(event.target.value)}
              />
            </FormField>
          </div>
          {compensation.error === null ? null : (
            <Alert tone="error" className="mt-3">
              {errorMessage(compensation.error)}
            </Alert>
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

      {notice === null ? null : <Alert tone="success">{notice}</Alert>}

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
    </AdminPage>
  )
}
