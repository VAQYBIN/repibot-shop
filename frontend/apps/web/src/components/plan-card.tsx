import { formatBytes, type Language, translate } from '@repibot/core'
import { Badge, Card } from '@repibot/ui'

export interface Plan {
  id: number
  code: string
  name: Record<string, string>
  description: Record<string, string> | null
  duration_days: number
  price_rub: string
  price_stars: number
  traffic_limit_bytes: number
  hwid_device_limit: number
  is_trial: boolean
}

export interface PlanCardProps {
  plan: Plan
  language: Language
}

function localizedText(values: Record<string, string>, language: Language, fallback: string) {
  return values[language] ?? values.ru ?? values.en ?? fallback
}

function durationText(days: number, language: Language): string {
  const template = translate(language, 'plans.per_days').replace('{days}', String(days))

  if (language === 'en') return template.replace(/days$/, days === 1 ? 'day' : 'days')

  const lastTwo = days % 100
  const last = days % 10
  const unit =
    lastTwo >= 11 && lastTwo <= 14
      ? 'дней'
      : last === 1
        ? 'день'
        : last >= 2 && last <= 4
          ? 'дня'
          : 'дней'
  return template.replace(/дней$/, unit)
}

function rublePrice(value: string, language: Language): string {
  const number = Number(value)
  return new Intl.NumberFormat(language, { maximumFractionDigits: 2 }).format(number)
}

const STAR_LABELS: Record<Language, Partial<Record<Intl.LDMLPluralRule, string>>> = {
  ru: { one: 'звезда', few: 'звезды', many: 'звёзд', other: 'звёзд' },
  en: { one: 'star', other: 'stars' },
}

function starsPrice(value: number, language: Language): string {
  const category = new Intl.PluralRules(language).select(value)
  const label = STAR_LABELS[language][category] ?? STAR_LABELS[language].other
  return `${new Intl.NumberFormat(language).format(value)} ${label}`
}

export function PlanCard({ plan, language }: PlanCardProps) {
  const name = localizedText(plan.name, language, plan.code)
  const description =
    plan.description === null ? null : localizedText(plan.description, language, '')

  return (
    <Card
      role="article"
      aria-labelledby={`plan-${plan.id}`}
      className={
        plan.is_trial
          ? 'bg-surface-sunken shadow-none md:grid md:grid-cols-[minmax(0,1fr)_minmax(16rem,0.7fr)] md:items-end md:gap-8'
          : 'flex h-full flex-col'
      }
    >
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h2 id={`plan-${plan.id}`} className="text-h2 font-semibold text-text">
            {name}
          </h2>
          {plan.is_trial ? (
            <Badge tone="info">{translate(language, 'plans.trial_badge')}</Badge>
          ) : null}
        </div>

        {description === null || description === '' ? null : (
          <p className="mt-2 max-w-[65ch] text-small text-text-secondary">{description}</p>
        )}

        <p className="mt-3 text-small text-text-secondary">
          {durationText(plan.duration_days, language)}
        </p>

        {plan.is_trial ? null : (
          <div className="mt-6 flex flex-wrap items-baseline gap-x-4 gap-y-1 tabular-nums">
            <p className="text-h1 font-semibold text-text">
              {rublePrice(plan.price_rub, language)} {translate(language, 'plans.price_rub')}
            </p>
            <p className="text-small text-text-secondary">
              {starsPrice(plan.price_stars, language)}
            </p>
          </div>
        )}
      </div>

      <dl
        className={
          plan.is_trial ? 'mt-6 grid grid-cols-2 gap-6 md:mt-0' : 'mt-8 grid grid-cols-2 gap-6'
        }
      >
        <div>
          <dt className="text-caption text-text-secondary">
            {translate(language, 'plans.traffic')}
          </dt>
          <dd className="mt-1 text-h3 font-medium tabular-nums text-text">
            {formatBytes(plan.traffic_limit_bytes, language, { zeroIsUnlimited: true })}
          </dd>
        </div>
        <div>
          <dt className="text-caption text-text-secondary">
            {translate(language, 'plans.devices')}
          </dt>
          <dd className="mt-1 text-h3 font-medium tabular-nums text-text">
            {plan.hwid_device_limit}
          </dd>
        </div>
      </dl>
    </Card>
  )
}
