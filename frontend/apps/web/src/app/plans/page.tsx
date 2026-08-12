'use client'

import { usePlans } from '@repibot/core'
import { Alert, Button, Card, EmptyState, Spinner } from '@repibot/ui'

import { PlanCard } from '@/components/plan-card'
import { useBrowserLanguage, useTranslate } from '@/lib/i18n'

export default function PlansPage() {
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const plans = usePlans()

  return (
    <main className="mx-auto min-h-dvh w-full max-w-5xl px-6 py-12 sm:py-16">
      <h1 className="text-h1 font-semibold text-text">{t('plans.title')}</h1>

      {plans.isPending ? (
        <Spinner label={t('common.loading')} className="mt-10 block" />
      ) : plans.isError ? (
        <Card className="mt-10">
          <Alert tone="error">{t('common.error')}</Alert>
          <div className="mt-4">
            <Button type="button" onClick={() => plans.refetch()}>
              {t('common.retry')}
            </Button>
          </div>
        </Card>
      ) : plans.data.length === 0 ? (
        <EmptyState className="mt-10" title={t('plans.empty')} />
      ) : (
        <ul className="mt-10 grid grid-cols-1 gap-4 md:grid-cols-2">
          {plans.data.map((plan) => (
            <li key={plan.id} className={plan.is_trial ? 'md:col-span-2' : undefined}>
              <PlanCard plan={plan} language={language} />
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
