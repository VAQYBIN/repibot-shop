'use client'

import type { CreateOrderRequest, Language } from '@repibot/core'
import { Button, Dialog } from '@repibot/ui'
import { useTranslate } from '@/lib/i18n'

export interface OrderDialogProps {
  open: boolean
  language: Language
  planName: string
  onClose: () => void
  onConfirm: () => void
  pending: boolean
}

/** Заказ-подарок требует явного подтверждения до создания серверного заказа. */
export function OrderDialog({
  open,
  language,
  planName,
  onClose,
  onConfirm,
  pending,
}: OrderDialogProps) {
  const t = useTranslate(language)
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t('payment.gift_confirm')}
      description={`${planName}. ${t('payment.gift_hint')}`}
    >
      <Button type="button" variant="ghost" onClick={onClose} disabled={pending}>
        {t('common.cancel')}
      </Button>
      <Button type="button" onClick={onConfirm} disabled={pending}>
        {pending ? t('common.loading') : t('payment.confirm')}
      </Button>
    </Dialog>
  )
}

export type OrderIntent = Pick<
  CreateOrderRequest,
  'plan_id' | 'purpose' | 'provider' | 'promo_code'
>
