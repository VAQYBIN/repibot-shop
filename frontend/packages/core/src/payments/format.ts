import type { components } from '../api/schema'
import type { Language, TranslationKey } from '../i18n/index'
import { translate } from '../i18n/index'

export type OrderResponse = components['schemas']['OrderResponse']

/**
 * Сумма берётся только из снимка заказа: витрина не пересчитывает скидки и
 * никогда не подменяет цену выбранного тарифа.
 */
export function formatOrderAmount(order: OrderResponse, language: Language): string {
  if (order.telegram_invoice_required) {
    return `${order.price_stars} ${translate(language, 'plans.price_stars')}`
  }

  return new Intl.NumberFormat(language, { style: 'currency', currency: 'RUB' }).format(
    Number(order.amount_due_rub),
  )
}

/** Статус — серверная истина; неизвестный переход остаётся ожиданием оплаты. */
export function formatPaymentStatus(
  order: Pick<OrderResponse, 'status'>,
  language: Language,
): string {
  const statuses: Partial<Record<string, TranslationKey>> = {
    pending: 'payment.status.pending',
    fulfilled: 'payment.status.fulfilled',
    expired: 'payment.status.expired',
    canceled: 'payment.status.canceled',
    refunded: 'payment.status.refunded',
  }
  const key = statuses[order.status] ?? 'payment.status.pending'

  return translate(language, key)
}
