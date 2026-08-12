import {
  formatDate,
  type OrderResponse,
  translate,
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
  Badge,
  type BadgeTone,
  Button,
  Card,
  Dialog,
  EmptyState,
  Input,
  Spinner,
  Switch,
} from '@repibot/ui'
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
/* Тот же тон, что в кабинете: оплачен — успех, ждёт — предупреждение,
   отменён или отклонён — отказ, всё остальное — нейтральный. */
function statusTone(status: OrderResponse['status']): BadgeTone {
  switch (status) {
    case 'succeeded':
    case 'fulfilled':
      return 'success'
    case 'pending':
      return 'warning'
    case 'canceled':
      return 'danger'
    default:
      return 'neutral'
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
  const card = usePaymentMethod()
  const unlinkCard = useUnlinkCard(language)
  const startBinding = useStartCardBinding(language)
  const [promo, setPromo] = useState('')
  const [voucher, setVoucher] = useState('')
  const [stars, setStars] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const [giftPlan, setGiftPlan] = useState<Plan | null>(null)
  const [unlinkAsked, setUnlinkAsked] = useState(false)
  const current = subscription.data?.subscription
  // Название карты приходит с сервера целиком; клиент не собирает его из
  // маски и платёжной системы, иначе разойдётся с тем, что видит бот.
  const cardTitle = card.data?.title ?? null
  const waitingForCard = card.data?.binding_pending === true
  async function bindCard() {
    let started: { confirmation_url: string | null }
    try {
      // Mini App живёт только внутри Telegram, поэтому возвращать плательщика
      // на сайт нельзя: сервер по этой поверхности уведёт его в чат бота.
      started = await startBinding.mutateAsync({ return_surface: 'miniapp' })
    } catch {
      return
    }
    if (started.confirmation_url) openTelegramUrl(started.confirmation_url)
  }
  async function order(
    plan: Plan,
    provider: 'yookassa' | 'stars',
    purpose: 'purchase' | 'renew' | 'gift' = 'purchase',
  ) {
    setStars(false)
    setAccepted(false)
    let created: OrderResponse
    try {
      created = await createOrder.mutateAsync({
        plan_id: plan.id,
        purpose,
        provider,
        promo_code: promo || null,
        idempotency_key: crypto.randomUUID(),
        // Форма провайдера открывается поверх Telegram: после оплаты человека
        // ждут в боте, а не на сайте, где Mini App просто не запустится.
        return_surface: 'miniapp',
      })
    } catch {
      return
    }
    setAccepted(promo !== '')
    if (provider === 'yookassa' && created.confirmation_url)
      openTelegramUrl(created.confirmation_url)
    // Mini App не проводит оплату Stars в браузере: инвойс выставляет бот.
    if (created.telegram_invoice_required) {
      setStars(true)
      if (created.telegram_handoff_url) openTelegramUrl(created.telegram_handoff_url, true)
    }
    setGiftPlan(null)
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
  return (
    <main className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">{translate(language, 'payment.title')}</h1>
      <Card>
        <label htmlFor="mini-promo" className="text-small font-medium text-text">
          {translate(language, 'payment.promo')}
        </label>
        <Input
          id="mini-promo"
          value={promo}
          onChange={(event) => setPromo(event.target.value)}
          className="mt-2"
        />
        {accepted ? (
          <p role="status" className="mt-2 text-small text-text-accent">
            {translate(language, 'payment.promo_applied')}
          </p>
        ) : null}
      </Card>
      <section aria-labelledby="mini-payment-plans">
        <h2 id="mini-payment-plans" className="text-h3 font-semibold text-text">
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
                    <p className="mt-1 text-small text-text-secondary">
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
        <Alert tone="error">{errorText(createOrder.error, language)}</Alert>
      ) : null}
      {stars ? (
        <Card>
          <p role="status" className="text-small text-text">
            {translate(language, 'payment.stars_instruction')}
          </p>
          <p className="mt-1 text-small text-text-secondary">
            {translate(language, 'payment.stars_handoff')}
          </p>
        </Card>
      ) : null}
      <Card>
        <h2 className="text-h3 font-semibold text-text">
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
          <Alert tone="error" className="mt-2">
            {errorText(redeem.error, language)}
          </Alert>
        ) : null}
        {gifts.isPending ? (
          <Spinner label={translate(language, 'common.loading')} className="mt-3" />
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
                  ? translate(language, 'payment.status.pending')
                  : translate(language, 'payment.status.fulfilled')}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card>
        <h2 className="text-h3 font-semibold text-text">{translate(language, 'payment.card')}</h2>
        {card.isPending ? (
          <Spinner label={translate(language, 'common.loading')} className="mt-2" />
        ) : cardTitle === null ? (
          <>
            <p className="mt-2 text-small text-text">{translate(language, 'payment.card_none')}</p>
            {/* Ответ провайдера идёт своим ходом; молчащий экран человек
                принимает за неудавшуюся привязку и начинает её заново. */}
            {waitingForCard ? (
              <p role="status" className="mt-1 text-small text-text-secondary">
                {translate(language, 'payment.card_waiting')}
              </p>
            ) : (
              <p className="mt-1 text-small text-text-secondary">
                {translate(language, 'payment.card_hint')}
              </p>
            )}
          </>
        ) : (
          <div className="mt-2 flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="truncate font-medium text-text">{cardTitle}</p>
              {card.data?.linked_at ? (
                <time className="text-small text-text-secondary" dateTime={card.data.linked_at}>
                  {formatDate(card.data.linked_at, language)}
                </time>
              ) : null}
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="shrink-0"
              aria-label={`${translate(language, 'payment.card_unlink')} ${cardTitle}`}
              disabled={unlinkCard.isPending}
              onClick={() => setUnlinkAsked(true)}
            >
              {translate(language, 'payment.card_unlink')}
            </Button>
          </div>
        )}
        {card.data?.binding_available === true ? (
          <div className="mt-3">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={startBinding.isPending}
              onClick={() => void bindCard()}
            >
              {translate(language, 'payment.card_bind')}
            </Button>
            <p className="mt-1 text-small text-text-secondary">
              {translate(language, 'payment.card_bind_hint')}
            </p>
          </div>
        ) : null}
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
        <div className="mt-4 border-t border-border-subtle pt-4">
          {current === null || current === undefined ? (
            <p className="text-small text-text-secondary">
              {translate(language, 'payment.auto_renew.unavailable')}
            </p>
          ) : (
            // Без карты списывать нечем: переключатель остаётся выключенным
            // и недоступным, чтобы не обещать продление, которого не будет.
            <Switch
              label={translate(language, 'payment.auto_renew')}
              checked={cardTitle !== null && current.auto_renew_enabled}
              disabled={autoRenew.isPending || cardTitle === null}
              onCheckedChange={(enabled) => void autoRenew.mutate({ auto_renew_enabled: enabled })}
            />
          )}
          {autoRenew.error !== null ? (
            <Alert tone="error" className="mt-2">
              {errorText(autoRenew.error, language)}
            </Alert>
          ) : null}
        </div>
      </Card>
      <section aria-labelledby="mini-orders">
        <h2 id="mini-orders" className="text-h3 font-semibold text-text">
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
                  <div className="mt-1 flex items-center gap-2">
                    <Badge tone={statusTone(item.status)}>{state(item, language)}</Badge>
                    <time className="text-small text-text-secondary" dateTime={item.expires_at}>
                      {formatDate(item.expires_at, language)}
                    </time>
                  </div>
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
      <Dialog
        open={unlinkAsked}
        onClose={() => setUnlinkAsked(false)}
        title={translate(language, 'payment.card_unlink_confirm')}
        description={translate(language, 'payment.card_unlink_hint')}
      >
        <Button type="button" variant="secondary" onClick={() => setUnlinkAsked(false)}>
          {translate(language, 'common.cancel')}
        </Button>
        <Button
          type="button"
          onClick={() => {
            unlinkCard.mutate()
            setUnlinkAsked(false)
          }}
        >
          {translate(language, 'payment.card_unlink')}
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
