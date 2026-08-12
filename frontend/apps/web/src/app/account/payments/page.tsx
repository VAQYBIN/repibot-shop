'use client'

import {
  type CardBindingResponse,
  formatDate,
  type OrderResponse,
  type TranslationKey,
  useAutoRenew,
  useCreateOrder,
  useGifts,
  useOrders,
  usePaymentMethod,
  usePlans,
  useRedeemGift,
  useStartCardBinding,
  useSubscription,
  useUnlinkCard,
} from '@repibot/core'
import {
  Alert,
  Button,
  Card,
  Dialog,
  EmptyState,
  Input,
  Spinner,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from '@repibot/ui'
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
  const paymentMethod = usePaymentMethod()
  const unlinkCard = useUnlinkCard(language)
  const startBinding = useStartCardBinding(language)
  const [promo, setPromo] = useState('')
  const [voucher, setVoucher] = useState('')
  const [giftPlan, setGiftPlan] = useState<Plan | null>(null)
  const [starsHint, setStarsHint] = useState(false)
  const [promoApplied, setPromoApplied] = useState(false)
  const [unlinkAsked, setUnlinkAsked] = useState(false)
  const current = subscription.data?.subscription
  const subscriptionReady = !subscription.isPending && subscription.error === null
  // Название карты приходит от сервера: собирать его на клиенте не из чего.
  const cardTitle = paymentMethod.data?.title ?? null
  const bindingAvailable = paymentMethod.data?.binding_available === true
  const waitingForCard = paymentMethod.data?.binding_pending === true

  function confirmUnlink() {
    setUnlinkAsked(false)
    unlinkCard.mutate()
  }

  async function startCardBinding() {
    let binding: CardBindingResponse
    try {
      // Привязку начали на сайте — сюда же провайдер и вернёт плательщика.
      binding = await startBinding.mutateAsync({ return_surface: 'web' })
    } catch {
      return
    }
    if (binding.confirmation_url !== null)
      window.open(binding.confirmation_url, '_blank', 'noopener,noreferrer')
  }

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
        // Оплату начали в браузере: адрес возврата сервер соберёт по сайту.
        return_surface: 'web',
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
        <h1 className="text-h1 font-semibold text-text">{t('payment.title')}</h1>
        <p className="mt-1 text-small text-text-secondary">{t('payment.retry_hint')}</p>
      </div>
      <Card>
        <label htmlFor="promo" className="text-small font-medium text-text">
          {t('payment.promo')}
        </label>
        <Input
          id="promo"
          value={promo}
          onChange={(event) => setPromo(event.target.value)}
          className="mt-2"
        />
        {promoApplied ? (
          <Alert tone="success" className="mt-2">
            {t('payment.promo_applied')}
          </Alert>
        ) : null}
      </Card>
      {plans.isPending ? (
        <Spinner label={t('common.loading')} />
      ) : plans.error !== null ? (
        <Card>
          <Alert tone="error">{errorText(plans.error, language)}</Alert>
          <Button className="mt-4" onClick={() => void plans.refetch()}>
            {t('common.retry')}
          </Button>
        </Card>
      ) : plans.data?.length === 0 ? (
        <EmptyState title={t('plans.empty')} />
      ) : (
        <section aria-labelledby="payment-plans">
          <h2 id="payment-plans" className="text-h3 font-medium text-text">
            {t('payment.choose_plan')}
          </h2>
          <ul className="mt-3 grid gap-3 md:grid-cols-2">
            {plans.data
              ?.filter((plan) => !plan.is_trial)
              .map((plan) => (
                <li key={plan.id}>
                  <Card>
                    <h3 className="text-h3 font-medium text-text">
                      {localized(plan.name, language, plan.code)}
                    </h3>
                    <p className="mt-1 text-small text-text-secondary">
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
      {subscription.isPending ? <Spinner label={t('common.loading')} /> : null}
      {createOrder.error !== null ? (
        <Alert tone="error">{errorText(createOrder.error, language)}</Alert>
      ) : null}
      {starsHint ? (
        <Card>
          <Alert tone="success">{t('payment.stars_instruction')}</Alert>
          <p className="mt-1 text-small text-text-secondary">{t('payment.stars_handoff')}</p>
        </Card>
      ) : null}
      <Card>
        <h2 className="text-h3 font-medium text-text">{t('payment.voucher')}</h2>
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
          <Alert tone="error" className="mt-2">
            {errorText(redeemGift.error, language)}
          </Alert>
        ) : null}
        {gifts.isPending ? (
          <Spinner label={t('common.loading')} className="mt-3" />
        ) : gifts.error !== null ? (
          <Alert tone="error" className="mt-3">
            {errorText(gifts.error, language)}
          </Alert>
        ) : gifts.data?.length === 0 ? null : (
          <ul className="mt-3 space-y-1 text-small text-text-secondary">
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
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-h3 font-medium text-text">{t('payment.card')}</h2>
            {paymentMethod.isPending ? (
              <Spinner label={t('common.loading')} className="mt-1" />
            ) : paymentMethod.error !== null ? (
              <Alert tone="error" className="mt-1">
                {errorText(paymentMethod.error, language)}
              </Alert>
            ) : cardTitle === null ? (
              <>
                <p className="mt-1 text-small text-text">{t('payment.card_none')}</p>
                {/* Ответ провайдера идёт своим ходом; молчащий экран человек
                    принимает за неудавшуюся привязку и начинает её заново. */}
                {waitingForCard ? (
                  <Spinner label={t('payment.card_waiting')} className="mt-1" />
                ) : (
                  <p className="mt-1 text-small text-text-secondary">{t('payment.card_hint')}</p>
                )}
              </>
            ) : (
              <p className="mt-1 text-small text-text">{cardTitle}</p>
            )}
            {bindingAvailable ? (
              <p className="mt-1 text-small text-text-secondary">{t('payment.card_bind_hint')}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {cardTitle === null ? null : (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={unlinkCard.isPending}
                onClick={() => setUnlinkAsked(true)}
              >
                {t('payment.card_unlink')}
              </Button>
            )}
            {bindingAvailable ? (
              <Button
                type="button"
                size="sm"
                disabled={startBinding.isPending}
                onClick={() => void startCardBinding()}
              >
                {t('payment.card_bind')}
              </Button>
            ) : null}
          </div>
        </div>
        {unlinkCard.error !== null ? (
          <Alert tone="error" className="mt-2">
            {errorText(unlinkCard.error, language)}
          </Alert>
        ) : null}
        {startBinding.error !== null ? (
          <Alert tone="error" className="mt-2">
            {errorText(startBinding.error, language)}
          </Alert>
        ) : null}
        <div className="mt-4 flex items-start justify-between gap-4 border-t border-border-subtle pt-4">
          <div>
            <h2 className="text-h3 font-medium text-text">{t('payment.auto_renew')}</h2>
            <p className="mt-1 text-small text-text-secondary">{t('payment.auto_renew_hint')}</p>
          </div>
          {subscription.error !== null ? (
            <div>
              <Alert tone="error">{errorText(subscription.error, language)}</Alert>
              <Button size="sm" className="mt-2" onClick={() => void subscription.refetch()}>
                {t('common.retry')}
              </Button>
            </div>
          ) : current === undefined || current === null ? (
            <p className="text-small text-text-secondary">{t('payment.auto_renew.unavailable')}</p>
          ) : (
            <Switch
              label={t('payment.auto_renew')}
              checked={current.auto_renew_enabled}
              // Без сохранённой карты списывать нечем: переключатель нечего
              // включать до того, как карта появится.
              disabled={autoRenew.isPending || cardTitle === null}
              onCheckedChange={(enabled) => void autoRenew.mutate({ auto_renew_enabled: enabled })}
            />
          )}
        </div>
        {autoRenew.error !== null ? (
          <Alert tone="error" className="mt-2">
            {errorText(autoRenew.error, language)}
          </Alert>
        ) : null}
      </Card>
      <Dialog
        open={unlinkAsked}
        onClose={() => setUnlinkAsked(false)}
        title={t('payment.card_unlink_confirm')}
        description={t('payment.card_unlink_hint')}
      >
        <Button type="button" variant="ghost" onClick={() => setUnlinkAsked(false)}>
          {t('common.cancel')}
        </Button>
        <Button type="button" onClick={confirmUnlink}>
          {t('payment.card_unlink')}
        </Button>
      </Dialog>
      <section aria-labelledby="orders">
        <h2 id="orders" className="text-h3 font-medium text-text">
          {t('payment.orders')}
        </h2>
        {orders.isPending ? (
          <Spinner label={t('common.loading')} className="mt-3" />
        ) : orders.error !== null ? (
          <Card className="mt-3">
            <Alert tone="error">{errorText(orders.error, language)}</Alert>
            <Button className="mt-3" onClick={() => void orders.refetch()}>
              {t('common.retry')}
            </Button>
          </Card>
        ) : orders.data?.length === 0 ? (
          <EmptyState className="mt-3" title={t('payment.orders_empty')} />
        ) : (
          <>
            {/* Ниже md таблица не помещается: восемь столбцов на четырёх
                дюймах превращаются в горизонтальную прокрутку каждой строки. */}
            <ul className="mt-3 space-y-2 md:hidden">
              {orders.data?.map((order) => (
                <li key={order.id}>
                  <Card>
                    <div className="flex justify-between gap-3">
                      <span className="font-medium text-text">
                        {localized(order.plan_name, language, order.plan_code)}
                      </span>
                      <span className="text-small text-text-secondary">
                        {orderStatus(order, t)}
                      </span>
                    </div>
                    <time
                      className="mt-1 block text-small text-text-secondary"
                      dateTime={order.expires_at}
                    >
                      {formatDate(order.expires_at, language)}
                    </time>
                  </Card>
                </li>
              ))}
            </ul>

            <div className="mt-3 hidden md:block">
              {/* Ключа "статус" отдельным словом в словаре нет: заголовок
                  столбца берёт тот же ключ, что и заголовок раздела/подпись
                  таблицы — новый ключ ради одного слова план заводить не даёт. */}
              <Table caption={t('payment.orders')}>
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>{t('plans.title')}</TableHeaderCell>
                    <TableHeaderCell>{t('subscription.expires_at')}</TableHeaderCell>
                    <TableHeaderCell>{t('payment.orders')}</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {orders.data?.map((order) => (
                    <TableRow key={order.id}>
                      <TableCell className="font-medium">
                        {localized(order.plan_name, language, order.plan_code)}
                      </TableCell>
                      <TableCell className="tabular-nums text-text-secondary">
                        <time dateTime={order.expires_at}>
                          {formatDate(order.expires_at, language)}
                        </time>
                      </TableCell>
                      <TableCell>{orderStatus(order, t)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
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
