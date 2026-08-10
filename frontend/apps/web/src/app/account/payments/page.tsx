'use client'

import {
  formatDate,
  type OrderResponse,
  type TranslationKey,
  useAutoRenew,
  useCreateOrder,
  useGifts,
  useOrders,
  usePlans,
  useRedeemGift,
  useSubscription,
} from '@repibot/core'
import { Button, Card, EmptyState, Input, Switch } from '@repibot/ui'
import { useState } from 'react'

import { OrderDialog } from '@/components/order-dialog'
import { errorText, useProfileLanguage, useTranslate } from '@/lib/i18n'

function localized(values: Record<string, string>, language: 'ru' | 'en', fallback: string) {
  return values[language] ?? values.ru ?? values.en ?? fallback
}
type Plan = { id: number; code: string; name: Record<string, string>; duration_days: number }
function orderStatus(order: OrderResponse, t: (key: TranslationKey) => string) {
  switch (order.status) {
    case 'succeeded':
    case 'fulfilled':
      return t('payment.status.fulfilled')
    case 'pending':
      return t('payment.status.pending')
    case 'expired':
      return t('payment.status.expired')
    case 'canceled':
      return t('payment.status.canceled')
    case 'refunded':
      return t('payment.status.refunded')
    default:
      return order.status
  }
}

export default function PaymentsPage() {
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const plans = usePlans()
  const orders = useOrders()
  const subscription = useSubscription()
  const createOrder = useCreateOrder(language)
  const redeemGift = useRedeemGift(language)
  const gifts = useGifts()
  const autoRenew = useAutoRenew(language)
  const [promo, setPromo] = useState('')
  const [voucher, setVoucher] = useState('')
  const [giftPlan, setGiftPlan] = useState<Plan | null>(null)
  const [starsHint, setStarsHint] = useState(false)
  const [promoApplied, setPromoApplied] = useState(false)
  const current = subscription.data?.subscription
  const subscriptionReady = !subscription.isPending && subscription.error === null

  async function submit(
    plan: Plan,
    provider: 'yookassa' | 'stars',
    purpose: 'purchase' | 'renew' | 'gift' = 'purchase',
  ) {
    if (provider === 'yookassa' && !subscriptionReady) return
    setStarsHint(false)
    setPromoApplied(false)
    let order: OrderResponse
    try {
      order = await createOrder.mutateAsync({
        plan_id: plan.id,
        provider,
        purpose,
        promo_code: promo || null,
        idempotency_key: crypto.randomUUID(),
      })
    } catch {
      return
    }
    setPromoApplied(promo !== '')
    if (provider === 'yookassa' && order.confirmation_url !== null)
      window.open(order.confirmation_url, '_blank', 'noopener,noreferrer')
    if (provider === 'stars' && order.telegram_invoice_required) {
      setStarsHint(true)
      if (order.telegram_handoff_url)
        window.open(order.telegram_handoff_url, '_blank', 'noopener,noreferrer')
    }
    setGiftPlan(null)
  }

  return (
    <main className="flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-text">{t('payment.title')}</h1>
        <p className="mt-1 text-sm text-text-secondary">{t('payment.retry_hint')}</p>
      </div>
      <Card>
        <label htmlFor="promo" className="text-sm font-medium text-text">
          {t('payment.promo')}
        </label>
        <Input
          id="promo"
          value={promo}
          onChange={(event) => setPromo(event.target.value)}
          className="mt-2"
        />
        {promoApplied ? (
          <p role="status" className="mt-2 text-sm text-text-accent">
            {t('payment.promo_applied')}
          </p>
        ) : null}
      </Card>
      {plans.isPending ? (
        <p role="status" className="text-text-secondary">
          {t('common.loading')}
        </p>
      ) : plans.error !== null ? (
        <Card>
          <p role="alert" className="text-danger">
            {errorText(plans.error, language)}
          </p>
          <Button className="mt-4" onClick={() => void plans.refetch()}>
            {t('common.retry')}
          </Button>
        </Card>
      ) : plans.data?.length === 0 ? (
        <EmptyState title={t('plans.empty')} />
      ) : (
        <section aria-labelledby="payment-plans">
          <h2 id="payment-plans" className="text-lg font-semibold text-text">
            {t('payment.choose_plan')}
          </h2>
          <ul className="mt-3 grid gap-3 md:grid-cols-2">
            {plans.data
              ?.filter((plan) => !plan.is_trial)
              .map((plan) => (
                <li key={plan.id}>
                  <Card>
                    <h3 className="text-lg font-semibold text-text">
                      {localized(plan.name, language, plan.code)}
                    </h3>
                    <p className="mt-1 text-sm text-text-secondary">
                      {t('plans.per_days').replace('{days}', String(plan.duration_days))}
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Button
                        disabled={!subscriptionReady}
                        onClick={() => void submit(plan, 'yookassa')}
                      >
                        {t('payment.pay_card')}
                      </Button>
                      <Button variant="secondary" onClick={() => void submit(plan, 'stars')}>
                        {t('payment.pay_stars')}
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={!subscriptionReady}
                        onClick={() => setGiftPlan(plan)}
                      >
                        {t('payment.gift')}
                      </Button>
                      {current === null || current === undefined ? null : (
                        <Button
                          disabled={!subscriptionReady}
                          variant="ghost"
                          onClick={() => void submit(plan, 'yookassa', 'renew')}
                        >
                          {t(current.plan_code === plan.code ? 'payment.renew' : 'payment.change')}
                        </Button>
                      )}
                    </div>
                  </Card>
                </li>
              ))}
          </ul>
        </section>
      )}
      {subscription.isPending ? (
        <p role="status" className="text-sm text-text-secondary">
          {t('common.loading')}
        </p>
      ) : null}
      {createOrder.error !== null ? (
        <p role="alert" className="text-sm text-danger">
          {errorText(createOrder.error, language)}
        </p>
      ) : null}
      {starsHint ? (
        <Card>
          <p role="status" className="text-sm text-text">
            {t('payment.stars_instruction')}
          </p>
          <p className="mt-1 text-sm text-text-secondary">{t('payment.stars_handoff')}</p>
        </Card>
      ) : null}
      <Card>
        <h2 className="text-lg font-semibold text-text">{t('payment.voucher')}</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <Input
            aria-label={t('payment.redeem_placeholder')}
            value={voucher}
            onChange={(event) => setVoucher(event.target.value)}
          />
          <Button
            disabled={!voucher || redeemGift.isPending}
            onClick={() => void redeemGift.mutateAsync({ code: voucher })}
          >
            {t('payment.redeem')}
          </Button>
        </div>
        {redeemGift.error !== null ? (
          <p role="alert" className="mt-2 text-sm text-danger">
            {errorText(redeemGift.error, language)}
          </p>
        ) : null}
        {gifts.isPending ? (
          <p role="status" className="mt-3 text-sm text-text-secondary">
            {t('common.loading')}
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
                  ? t('payment.status.pending')
                  : t('payment.status.fulfilled')}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-text">{t('payment.auto_renew')}</h2>
            <p className="mt-1 text-sm text-text-secondary">{t('payment.auto_renew_hint')}</p>
          </div>
          {subscription.error !== null ? (
            <div>
              <p role="alert" className="text-sm text-danger">
                {errorText(subscription.error, language)}
              </p>
              <Button size="sm" className="mt-2" onClick={() => void subscription.refetch()}>
                {t('common.retry')}
              </Button>
            </div>
          ) : current === undefined || current === null ? (
            <p className="text-sm text-text-secondary">{t('payment.auto_renew.unavailable')}</p>
          ) : (
            <Switch
              label={t('payment.auto_renew')}
              checked={current.auto_renew_enabled}
              disabled={autoRenew.isPending}
              onCheckedChange={(enabled) => void autoRenew.mutate({ auto_renew_enabled: enabled })}
            />
          )}
        </div>
        {autoRenew.error !== null ? (
          <p role="alert" className="mt-2 text-sm text-danger">
            {errorText(autoRenew.error, language)}
          </p>
        ) : null}
      </Card>
      <section aria-labelledby="orders">
        <h2 id="orders" className="text-lg font-semibold text-text">
          {t('payment.orders')}
        </h2>
        {orders.isPending ? (
          <p role="status" className="mt-3 text-text-secondary">
            {t('common.loading')}
          </p>
        ) : orders.error !== null ? (
          <Card className="mt-3">
            <p role="alert" className="text-danger">
              {errorText(orders.error, language)}
            </p>
            <Button className="mt-3" onClick={() => void orders.refetch()}>
              {t('common.retry')}
            </Button>
          </Card>
        ) : orders.data?.length === 0 ? (
          <EmptyState className="mt-3" title={t('payment.orders_empty')} />
        ) : (
          <ul className="mt-3 space-y-2">
            {orders.data?.map((order) => (
              <li key={order.id}>
                <Card>
                  <div className="flex justify-between gap-3">
                    <span className="font-medium text-text">
                      {localized(order.plan_name, language, order.plan_code)}
                    </span>
                    <span className="text-sm text-text-secondary">{orderStatus(order, t)}</span>
                  </div>
                  <time
                    className="mt-1 block text-sm text-text-secondary"
                    dateTime={order.expires_at}
                  >
                    {formatDate(order.expires_at, language)}
                  </time>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>
      <OrderDialog
        open={giftPlan !== null}
        language={language}
        planName={giftPlan === null ? '' : localized(giftPlan.name, language, giftPlan.code)}
        pending={createOrder.isPending}
        onClose={() => setGiftPlan(null)}
        onConfirm={() => {
          if (giftPlan !== null) void submit(giftPlan, 'yookassa', 'gift')
        }}
      />
    </main>
  )
}
