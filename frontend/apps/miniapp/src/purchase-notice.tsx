import { type TranslationKey, translate, usePurchaseNotice } from '@repibot/core'
import { Button, Dialog } from '@repibot/ui'

import { useLanguage } from './api'

/** Что именно случилось: покупка, продление и подарок — разные новости. */
const OUTCOME: Record<string, TranslationKey> = {
  purchase: 'payment.paid_purchase',
  renew: 'payment.paid_renew',
  gift: 'payment.paid_gift',
}

/**
 * Окно об оплаченном заказе.
 *
 * Живёт в общей разметке, а не на экране оплаты: человек уходит платить в
 * браузер и возвращается на ту вкладку, которую сам выберет. Уведомление от
 * бота приходит в переписку, куда он в этот момент не смотрит.
 */
export function PurchaseNotice() {
  const language = useLanguage()
  const { order, dismiss } = usePurchaseNotice()
  const outcome = order === null ? undefined : OUTCOME[order.purpose]

  return (
    <Dialog
      open={order !== null}
      onClose={dismiss}
      title={translate(language, 'payment.paid_title')}
      description={outcome === undefined ? undefined : translate(language, outcome)}
    >
      <Button type="button" onClick={dismiss}>
        {translate(language, 'common.close')}
      </Button>
    </Dialog>
  )
}
