'use client'

import { formatDate, type Language, translate } from '@repibot/core'
import { Button, Card } from '@repibot/ui'
import QRCode from 'qrcode'
import { useEffect, useState } from 'react'

export interface Subscription {
  plan_code: string
  plan_name: Record<string, string>
  status: string
  started_at: string
  expires_at: string
  subscription_url: string | null
  traffic_limit_bytes: number
  hwid_device_limit: number
}

interface SubscriptionCardProps {
  subscription: Subscription
  language: Language
}

function planName(subscription: Subscription, language: Language): string {
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

function isUsable(status: string): boolean {
  return status === 'active' || status === 'trial'
}

export function SubscriptionCard({ subscription, language }: SubscriptionCardProps) {
  const [qr, setQr] = useState<string | null>(null)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle')
  const url = isUsable(subscription.status) ? subscription.subscription_url : null

  useEffect(() => {
    let current = true
    setQr(null)

    if (url !== null) {
      QRCode.toString(url, { type: 'svg', margin: 1 }).then((svg) => {
        if (current) setQr(svg)
      })
    }

    return () => {
      current = false
    }
  }, [url])

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
    <Card role="region" aria-labelledby="current-subscription-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="current-subscription-title" className="text-xl font-semibold text-text">
            {planName(subscription, language)}
          </h2>
          <p className="mt-1 text-sm font-medium text-text-accent">
            {statusText(subscription.status, language)}
          </p>
        </div>
        <div className="text-right tabular-nums">
          <p className="text-xs text-text-secondary">
            {translate(language, 'subscription.expires_at')}
          </p>
          <time dateTime={subscription.expires_at} className="mt-1 block text-sm text-text">
            {formatDate(subscription.expires_at, language)}
          </time>
        </div>
      </div>

      {subscription.status === 'pending_provision' ? (
        <p className="mt-5 text-sm text-text-secondary">
          {translate(language, 'subscription.pending_hint')}
        </p>
      ) : null}

      {url === null ? null : (
        <div className="mt-6 grid gap-5 sm:grid-cols-[minmax(0,1fr)_9rem] sm:items-start">
          <div className="min-w-0">
            <p className="text-sm font-medium text-text">
              {translate(language, 'subscription.link')}
            </p>
            <a
              href={url}
              className="mt-2 block break-all text-sm text-text-accent underline underline-offset-4"
            >
              {url}
            </a>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button type="button" size="sm" onClick={copyUrl}>
                {translate(language, 'subscription.copy')}
              </Button>
              {copyState === 'idle' ? null : (
                <span
                  role={copyState === 'copied' ? 'status' : 'alert'}
                  className={
                    copyState === 'copied' ? 'text-sm text-text-secondary' : 'text-sm text-danger'
                  }
                >
                  {copyState === 'copied'
                    ? translate(language, 'subscription.copied')
                    : translate(language, 'common.error')}
                </span>
              )}
            </div>
          </div>

          {qr === null ? (
            <div
              role="status"
              aria-label={translate(language, 'subscription.qr')}
              className="aspect-square rounded-md bg-surface-sunken"
            />
          ) : (
            <div
              role="img"
              aria-label={translate(language, 'subscription.qr')}
              className="aspect-square overflow-hidden rounded-md bg-white p-2 [&_svg]:h-full [&_svg]:w-full"
              // biome-ignore lint/security/noDangerouslySetInnerHtml: qrcode создаёт SVG локально из экранированной строки URL.
              dangerouslySetInnerHTML={{ __html: qr }}
            />
          )}
        </div>
      )}
    </Card>
  )
}
