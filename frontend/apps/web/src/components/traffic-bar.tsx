'use client'

import { formatBytes, type Language, translate, useTraffic } from '@repibot/core'
import { Alert, Card, Spinner } from '@repibot/ui'

import { errorText } from '@/lib/i18n'

interface TrafficBarProps {
  language: Language
}

export function TrafficBar({ language }: TrafficBarProps) {
  const traffic = useTraffic()

  return (
    <Card role="region" aria-labelledby="traffic-title">
      {/* Внутри карточки заголовок второго уровня не должен спорить с
          заголовком страницы. */}
      <h2 id="traffic-title" className="text-h3 font-medium text-text">
        {translate(language, 'traffic.title')}
      </h2>

      {traffic.isPending ? (
        <Spinner label={translate(language, 'common.loading')} className="mt-4 block" />
      ) : traffic.error !== null ? (
        <Alert tone="error" className="mt-4">
          {errorText(traffic.error, language)}
        </Alert>
      ) : traffic.data === undefined ? null : (
        <div className="mt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-small">
            <p className="text-text-secondary">{translate(language, 'traffic.used')}</p>
            <p className="font-medium tabular-nums text-text">
              {formatBytes(traffic.data.used_bytes, language)}
              {traffic.data.limit_bytes === 0
                ? ` · ${translate(language, 'traffic.unlimited')}`
                : ` / ${formatBytes(traffic.data.limit_bytes, language)}`}
            </p>
          </div>

          {traffic.data.limit_bytes === 0 ? null : (
            <div
              role="progressbar"
              aria-label={translate(language, 'traffic.used')}
              aria-valuemin={0}
              aria-valuemax={traffic.data.limit_bytes}
              aria-valuenow={Math.min(traffic.data.used_bytes, traffic.data.limit_bytes)}
              className="mt-3 h-2 overflow-hidden rounded-full bg-surface-sunken"
            >
              <div
                className="h-full rounded-full bg-accent"
                style={{
                  width: `${Math.min(
                    100,
                    (traffic.data.used_bytes / traffic.data.limit_bytes) * 100,
                  )}%`,
                }}
              />
            </div>
          )}

          {traffic.data.used_bytes === 0 && traffic.data.days.length === 0 ? (
            <p className="mt-4 text-small text-text-secondary">
              {language === 'ru' ? 'Трафик пока не использован' : 'No traffic used yet'}
            </p>
          ) : null}

          {traffic.data.days.length === 0 ? null : (
            <div className="mt-5 border-t border-border-subtle pt-4">
              <p className="text-caption text-text-secondary">
                {translate(language, 'traffic.last_days')}
              </p>
              <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                {traffic.data.days.map((day) => (
                  <div key={day.day} className="flex justify-between gap-4 text-small tabular-nums">
                    <dt className="text-text-secondary">
                      {new Intl.DateTimeFormat(language, { dateStyle: 'medium' }).format(
                        new Date(`${day.day}T12:00:00Z`),
                      )}
                    </dt>
                    <dd className="text-text">{formatBytes(day.used_bytes, language)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
