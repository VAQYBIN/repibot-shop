'use client'

import { useActivateTrial, useSubscription } from '@repibot/core'
import { Button, EmptyState } from '@repibot/ui'
import Link from 'next/link'

import { DeviceList } from '@/components/device-list'
import { SubscriptionCard } from '@/components/subscription-card'
import { TrafficBar } from '@/components/traffic-bar'
import { errorText, useProfileLanguage, useTranslate } from '@/lib/i18n'

export default function SubscriptionPage() {
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const subscription = useSubscription()
  const trial = useActivateTrial(language)
  const current = subscription.data?.subscription
  // В публичном ответе нет remnawave_id. Единственный доступный клиенту
  // признак незавершённого provisioning — сам статус pending_provision.
  const panelAvailable =
    current !== undefined && current !== null && current.status !== 'pending_provision'

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{t('subscription.title')}</h1>

      {subscription.isPending ? (
        <p role="status" className="text-text-secondary">
          {t('common.loading')}
        </p>
      ) : subscription.error !== null ? (
        <p role="alert" className="text-sm text-danger">
          {errorText(subscription.error, language)}
        </p>
      ) : subscription.data?.subscription === null ? (
        <EmptyState
          title={t('subscription.none')}
          action={
            subscription.data.trial_available ? (
              <Button type="button" onClick={() => trial.mutate()} disabled={trial.isPending}>
                {t('subscription.trial_cta')}
              </Button>
            ) : undefined
          }
        />
      ) : subscription.data?.subscription === undefined ? null : (
        <SubscriptionCard subscription={subscription.data.subscription} language={language} />
      )}

      {trial.error === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {errorText(trial.error, language)}
        </p>
      )}

      <Link
        href="/account/payments"
        className="text-sm font-medium text-text-accent underline underline-offset-4"
      >
        {t('payment.title')}
      </Link>

      {panelAvailable ? (
        <>
          <TrafficBar language={language} />
          <DeviceList language={language} />
        </>
      ) : null}
    </main>
  )
}
