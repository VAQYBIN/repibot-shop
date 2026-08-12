'use client'

import { useActivateTrial, useSubscription } from '@repibot/core'
import { Alert, Button, EmptyState, Spinner } from '@repibot/ui'
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
    <main className="flex flex-col gap-6">
      <h1 className="text-h1 font-semibold text-text">{t('subscription.title')}</h1>

      {subscription.isPending ? (
        <Spinner label={t('common.loading')} />
      ) : subscription.error !== null ? (
        <Alert tone="error">{errorText(subscription.error, language)}</Alert>
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

      {trial.error === null ? null : <Alert tone="error">{errorText(trial.error, language)}</Alert>}

      <div>
        <Button asChild variant="secondary" size="sm">
          <Link href="/account/payments">{t('payment.title')}</Link>
        </Button>
      </div>

      {panelAvailable ? (
        <>
          <TrafficBar language={language} />
          <DeviceList language={language} />
        </>
      ) : null}
    </main>
  )
}
