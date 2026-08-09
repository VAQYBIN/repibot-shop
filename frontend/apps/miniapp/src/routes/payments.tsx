import {
  formatDate,
  type OrderResponse,
  translate,
  useAutoRenew,
  useCreateOrder,
  useGifts,
  useOrders,
  usePlans,
  useRedeemGift,
  useSubscription,
} from '@repibot/core'
import { Button, Card, Dialog, EmptyState, Input, Switch } from '@repibot/ui'
import { createRoute } from '@tanstack/react-router'
import { useState } from 'react'

import { useLanguage } from '../api'
import { Loading, Retry } from '../auth-fallback'
import { openTelegramUrl } from '../telegram'
import { rootRoute } from './root'

function name(values: Record<string, string>, language: 'ru' | 'en', fallback: string) {
  return values[language] ?? values.ru ?? values.en ?? fallback
}
type Plan = { id: number; code: string; name: Record<string, string>; duration_days: number }
function errorText(error: unknown, language: 'ru' | 'en') {
  return error instanceof Error && error.message
    ? error.message
    : translate(language, 'common.error')
}
function state(order: OrderResponse, language: 'ru' | 'en') {
  switch (order.status) {
    case 'succeeded':
    case 'fulfilled':
      return translate(language, 'payment.status.fulfilled')
    case 'pending':
      return translate(language, 'payment.status.pending')
    case 'expired':
      return translate(language, 'payment.status.expired')
    case 'canceled':
      return translate(language, 'payment.status.canceled')
    case 'refunded':
      return translate(language, 'payment.status.refunded')
    default:
      return order.status
  }
}

export function Payments() {
  const language = useLanguage()
  const plans = usePlans()
  const orders = useOrders()
  const subscription = useSubscription()
  const createOrder = useCreateOrder(language)
  const redeem = useRedeemGift(language)
  const gifts = useGifts()
  const autoRenew = useAutoRenew(language)
  const [promo, setPromo] = useState('')
  const [voucher, setVoucher] = useState('')
  const [stars, setStars] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const [giftPlan, setGiftPlan] = useState<Plan | null>(null)
  async function order(
    plan: Plan,
    provider: 'yookassa' | 'stars',
    purpose: 'purchase' | 'renew' | 'gift' = 'purchase',
  ) {
    setStars(false)
    setAccepted(false)
    let created
    try {
      created = await createOrder.mutateAsync({
        plan_id: plan.id,
        purpose,
        provider,
        promo_code: promo || null,
        save_payment_method: false,
        idempotency_key: crypto.randomUUID(),
      })
    } catch {
      return
    }
    setAccepted(promo !== '')
    if (provider === 'yookassa' && created.confirmation_url)
      openTelegramUrl(created.confirmation_url)
    // Mini App never settles Stars in a browser. Telegram's bot owns the invoice.
    if (created.telegram_invoice_required) {
      setStars(true)
      if (created.telegram_handoff_url) openTelegramUrl(created.telegram_handoff_url, true)
    }
  }
  if (plans.isPending || orders.isPending || subscription.isPending)
    return <Loading language={language} />
  if (plans.error !== null)
    return (
      <Retry
        language={language}
        message={errorText(plans.error, language)}
        onRetry={() => void plans.refetch()}
      />
    )
  if (subscription.error !== null)
    return (
      <Retry
        language={language}
        message={errorText(subscription.error, language)}
        onRetry={() => void subscription.refetch()}
      />
    )
  const current = subscription.data?.subscription
  return (
    <main className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{translate(language, 'payment.title')}</h1>
      <Card>
        <label htmlFor="mini-promo" className="text-sm font-medium text-text">
          {translate(language, 'payment.promo')}
        </label>
        <Input
          id="mini-promo"
          value={promo}
          onChange={(event) => setPromo(event.target.value)}
          className="mt-2"
        />
        {accepted ? (
          <p role="status" className="mt-2 text-sm text-text-accent">
            {translate(language, 'payment.promo_applied')}
          </p>
        ) : null}
      </Card>
      <section aria-labelledby="mini-payment-plans">
        <h2 id="mini-payment-plans" className="text-lg font-semibold text-text">
          {translate(language, 'payment.choose_plan')}
        </h2>
        {plans.data?.length === 0 ? (
          <EmptyState className="mt-3" title={translate(language, 'plans.empty')} />
        ) : (
          <ul className="mt-3 space-y-3">
            {plans.data
              ?.filter((plan) => !plan.is_trial)
              .map((plan) => (
                <li key={plan.id}>
                  <Card>
                    <h3 className="font-semibold text-text">
                      {name(plan.name, language, plan.code)}
                    </h3>
                    <p className="mt-1 text-sm text-text-secondary">
                      {translate(language, 'plans.per_days').replace(
                        '{days}',
                        String(plan.duration_days),
                      )}
                    </p>
                    <div className="mt-3 flex gap-2">
                      <Button onClick={() => void order(plan, 'stars')}>
                        {translate(language, 'payment.pay_stars')}
                      </Button>
                      <Button variant="secondary" onClick={() => void order(plan, 'yookassa')}>
                        {translate(language, 'payment.pay_card')}
                      </Button>
                      <Button variant="ghost" onClick={() => setGiftPlan(plan)}>
                        {translate(language, 'payment.gift')}
                      </Button>
                      {current === null || current === undefined ? null : (
                        <Button
                          variant="ghost"
                          onClick={() => void order(plan, 'yookassa', 'renew')}
                        >
                          {translate(
                            language,
                            current.plan_code === plan.code ? 'payment.renew' : 'payment.change',
                          )}
                        </Button>
                      )}
                    </div>
                  </Card>
                </li>
              ))}
          </ul>
        )}
      </section>
      {createOrder.error !== null ? (
        <p role="alert" className="text-sm text-danger">
          {errorText(createOrder.error, language)}
        </p>
      ) : null}
      {stars ? (
        <Card>
          <p role="status" className="text-sm text-text">
            {translate(language, 'payment.stars_instruction')}
          </p>
          <p className="mt-1 text-sm text-text-secondary">
            {translate(language, 'payment.stars_handoff')}
          </p>
        </Card>
      ) : null}
      <Card>
        <h2 className="text-lg font-semibold text-text">
          {translate(language, 'payment.voucher')}
        </h2>
        <div className="mt-3 flex gap-2">
          <Input
            aria-label={translate(language, 'payment.redeem_placeholder')}
            value={voucher}
            onChange={(event) => setVoucher(event.target.value)}
          />
          <Button
            disabled={!voucher || redeem.isPending}
            onClick={() => void redeem.mutate({ code: voucher })}
          >
            {translate(language, 'payment.redeem')}
          </Button>
        </div>
        {redeem.error !== null ? (
          <p role="alert" className="mt-2 text-sm text-danger">
            {errorText(redeem.error, language)}
          </p>
        ) : null}
        {gifts.isPending ? (
          <p role="status" className="mt-3 text-sm text-text-secondary">
            {translate(language, 'common.loading')}
          </p>
        ) : gifts.error !== null ? (
          <p role="alert" className="mt-3 text-sm text-danger">
            {errorText(gifts.error, language)}
          </p>
        ) : gifts.data?.length === 0 ? null : (
          <ul className="mt-3 space-y-1 text-sm text-text-secondary">
            {gifts.data?.map((gift) => (
              <li key={gift.code}>
                {gift.code} —{' '}
                {gift.redeemed_at === null
                  ? translate(language, 'payment.status.pending')
                  : translate(language, 'payment.status.fulfilled')}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        {current === null || current === undefined ? (
          <p className="text-sm text-text-secondary">
            {translate(language, 'payment.auto_renew.unavailable')}
          </p>
        ) : (
          <Switch
            label={translate(language, 'payment.auto_renew')}
            checked={current.auto_renew_enabled}
            disabled={autoRenew.isPending}
            onCheckedChange={(enabled) => void autoRenew.mutate({ auto_renew_enabled: enabled })}
          />
        )}
        {autoRenew.error !== null ? (
          <p role="alert" className="mt-2 text-sm text-danger">
            {errorText(autoRenew.error, language)}
          </p>
        ) : null}
      </Card>
      <section aria-labelledby="mini-orders">
        <h2 id="mini-orders" className="text-lg font-semibold text-text">
          {translate(language, 'payment.orders')}
        </h2>
        {orders.error !== null ? (
          <Retry
            language={language}
            message={errorText(orders.error, language)}
            onRetry={() => void orders.refetch()}
          />
        ) : orders.data?.length === 0 ? (
          <EmptyState className="mt-3" title={translate(language, 'payment.orders_empty')} />
        ) : (
          <ul className="mt-3 space-y-2">
            {orders.data?.map((item) => (
              <li key={item.id}>
                <Card>
                  <p className="font-medium text-text">
                    {name(item.plan_name, language, item.plan_code)}
                  </p>
                  <p className="text-sm text-text-secondary">{state(item, language)}</p>
                  <time className="text-sm text-text-secondary" dateTime={item.expires_at}>
                    {formatDate(item.expires_at, language)}
                  </time>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>
      <Dialog
        open={giftPlan !== null}
        onClose={() => setGiftPlan(null)}
        title={translate(language, 'payment.gift_confirm')}
        description={translate(language, 'payment.gift_hint')}
      >
        <Button variant="ghost" onClick={() => setGiftPlan(null)}>
          {translate(language, 'common.cancel')}
        </Button>
        <Button
          disabled={createOrder.isPending}
          onClick={() => {
            if (giftPlan) void order(giftPlan, 'yookassa', 'gift')
          }}
        >
          {translate(language, 'payment.confirm')}
        </Button>
      </Dialog>
    </main>
  )
}

export const paymentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/payments',
  component: Payments,
})
