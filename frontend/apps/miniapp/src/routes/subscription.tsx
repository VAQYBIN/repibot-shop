import {
  errorMessageKey,
  formatDate,
  type Language,
  translate,
  useActivateTrial,
  useSubscription,
} from '@repibot/core'
import { Alert, Button, Card, EmptyState } from '@repibot/ui'
import { createRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useLanguage } from '../api'
import { Loading, Retry } from '../auth-fallback'
import { useMainButton } from '../main-button'
import { haptic } from '../telegram'
import { rootRoute } from './root'

interface CurrentSubscription {
  plan_code: string
  plan_name: Record<string, string>
  status: string
  expires_at: string
  subscription_url: string | null
}

function mutationErrorText(error: unknown, language: Language): string {
  if (error instanceof Error && error.message !== '') return error.message
  const code = (error as { error?: { code?: string } } | undefined)?.error?.code
  return translate(language, errorMessageKey(code))
}

function queryErrorText(error: unknown, language: Language): string {
  const code = (error as { error?: { code?: string } } | undefined)?.error?.code
  return code === undefined
    ? translate(language, 'common.error')
    : translate(language, errorMessageKey(code))
}

function planName(subscription: CurrentSubscription, language: Language): string {
  return (
    subscription.plan_name[language] ??
    subscription.plan_name.ru ??
    subscription.plan_name.en ??
    subscription.plan_code
  )
}

function statusText(status: string, language: Language): string {
  switch (status) {
    case 'trial':
      return translate(language, 'subscription.status.trial')
    case 'active':
      return translate(language, 'subscription.status.active')
    case 'expired':
      return translate(language, 'subscription.status.expired')
    case 'disabled':
      return translate(language, 'subscription.status.disabled')
    case 'pending_provision':
      return translate(language, 'subscription.status.pending_provision')
    default:
      return status
  }
}

function SubscriptionDetails({
  subscription,
  language,
}: {
  subscription: CurrentSubscription
  language: Language
}) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const url =
    subscription.status === 'active' || subscription.status === 'trial'
      ? subscription.subscription_url
      : null

  async function copyUrl() {
    if (url === null) return
    try {
      await navigator.clipboard.writeText(url)
      setCopyState('copied')
    } catch {
      setCopyState('error')
    }
  }

  return (
    <Card role="region" aria-labelledby="miniapp-subscription-plan">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id="miniapp-subscription-plan" className="truncate text-h2 font-semibold text-text">
            {planName(subscription, language)}
          </h2>
          <p className="mt-1 text-small font-medium text-text-accent">
            {statusText(subscription.status, language)}
          </p>
        </div>
        <div className="shrink-0 text-right tabular-nums">
          <p className="text-caption text-text-secondary">
            {translate(language, 'subscription.expires_at')}
          </p>
          <time dateTime={subscription.expires_at} className="mt-1 block text-small text-text">
            {formatDate(subscription.expires_at, language)}
          </time>
        </div>
      </div>

      {subscription.status === 'pending_provision' ? (
        <p className="mt-5 text-small text-text-secondary">
          {translate(language, 'subscription.pending_hint')}
        </p>
      ) : null}

      {url === null ? null : (
        <div className="mt-6 border-t border-border-subtle pt-5">
          <p className="text-small font-medium text-text">
            {translate(language, 'subscription.link')}
          </p>
          <a
            href={url}
            className="mt-2 block break-all text-small text-text-accent underline underline-offset-4"
          >
            {url}
          </a>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button type="button" size="sm" onClick={copyUrl}>
              {translate(language, 'subscription.copy')}
            </Button>
          </div>
          {copyState === 'idle' ? null : copyState === 'copied' ? (
            <p role="status" className="mt-3 text-small text-text-secondary">
              {translate(language, 'subscription.copied')}
            </p>
          ) : (
            <Alert tone="error" className="mt-3">
              {translate(language, 'common.error')}
            </Alert>
          )}
        </div>
      )}
    </Card>
  )
}

export function Subscription() {
  const language = useLanguage()
  const subscription = useSubscription()
  const trial = useActivateTrial(language)
  const navigate = useNavigate()

  const current = subscription.data?.subscription
  // Пока подписки нет: доступное действие — либо бесплатный пробный период,
  // либо переход к оплате, если триал уже использован.
  const canActivate = current === null && subscription.data?.trial_available === true
  const canCheckout = current === null && subscription.data?.trial_available === false

  function activateTrial() {
    trial.mutate(undefined, {
      onSuccess: () => haptic('success'),
      onError: () => haptic('error'),
    })
  }

  const { supported } = useMainButton({
    text: translate(language, canActivate ? 'subscription.trial_cta' : 'payment.choose_plan'),
    onClick: () => {
      if (canActivate) activateTrial()
      else void navigate({ to: '/payments' })
    },
    visible: canActivate || canCheckout,
    loading: canActivate && trial.isPending,
  })

  if (subscription.isPending) return <Loading language={language} />
  if (subscription.error !== null) {
    return (
      <Retry
        language={language}
        message={queryErrorText(subscription.error, language)}
        onRetry={() => void subscription.refetch()}
      />
    )
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">
        {translate(language, 'subscription.title')}
      </h1>

      {current === null ? (
        <EmptyState
          title={translate(language, 'subscription.none')}
          action={
            supported ? undefined : canActivate ? (
              // Клиенты без главной кнопки Телеграма обязаны остаться рабочими:
              // без этой ветки бесплатный период в них не активировать.
              <Button type="button" onClick={activateTrial} disabled={trial.isPending}>
                {translate(language, 'subscription.trial_cta')}
              </Button>
            ) : canCheckout ? (
              <Button type="button" onClick={() => void navigate({ to: '/payments' })}>
                {translate(language, 'payment.choose_plan')}
              </Button>
            ) : undefined
          }
        />
      ) : current === undefined ? null : (
        <SubscriptionDetails subscription={current} language={language} />
      )}

      {trial.error === null ? null : (
        <Alert tone="error">{mutationErrorText(trial.error, language)}</Alert>
      )}
    </main>
  )
}

export const subscriptionRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/subscription',
  component: Subscription,
})
