'use client'

import { formatBytes, type Language, translate, useTraffic } from '@repibot/core'
import { Card } from '@repibot/ui'

import { errorText } from '@/lib/i18n'

interface TrafficBarProps {
  language: Language
}

export function TrafficBar({ language }: TrafficBarProps) {
  const traffic = useTraffic()

  return (
    <Card role="region" aria-labelledby="traffic-title">
      <h2 id="traffic-title" className="text-lg font-semibold text-text">
        {translate(language, 'traffic.title')}
      </h2>

      {traffic.isPending ? (
        <p role="status" className="mt-4 text-sm text-text-secondary">
          {translate(language, 'common.loading')}
        </p>
      ) : traffic.error !== null ? (
        <p role="alert" className="mt-4 text-sm text-danger">
          {errorText(traffic.error, language)}
        </p>
      ) : traffic.data === undefined ? null : (
        <div className="mt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
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

          {traffic.data.days.length === 0 ? null : (
            <div className="mt-5 border-t border-border-subtle pt-4">
              <p className="text-xs text-text-secondary">
                {translate(language, 'traffic.last_days')}
              </p>
              <dl className="mt-2 grid gap-2 sm:grid-cols-2">
                {traffic.data.days.map((day) => (
                  <div key={day.day} className="flex justify-between gap-4 text-sm tabular-nums">
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
