import {
  errorMessageKey,
  type Language,
  translate,
  useDevices,
  useUnlinkDevice,
} from '@repibot/core'
import { Button, Card, Dialog, EmptyState } from '@repibot/ui'
import { createRoute } from '@tanstack/react-router'
import { useState } from 'react'

import { useLanguage } from '../api'
import { Loading, Retry } from '../auth-fallback'
import { rootRoute } from './root'

interface Device {
  hwid: string
  platform: string | null
  device_model: string | null
  os_version: string | null
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

function deviceName(device: Device, language: Language): string {
  return device.device_model ?? device.platform ?? translate(language, 'devices.unknown_platform')
}

export function Devices() {
  const language = useLanguage()
  const devices = useDevices()
  const unlink = useUnlinkDevice(language)
  const [pending, setPending] = useState<Device | null>(null)

  if (devices.isPending) return <Loading language={language} />
  if (devices.error !== null) {
    return (
      <Retry
        language={language}
        message={queryErrorText(devices.error, language)}
        onRetry={() => void devices.refetch()}
      />
    )
  }

  function confirmUnlink() {
    if (pending === null) return
    unlink.mutate(pending.hwid)
    setPending(null)
  }

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{translate(language, 'devices.title')}</h1>

      <Card>
        <p className="text-sm tabular-nums text-text-secondary">
          {devices.data === undefined
            ? null
            : translate(language, 'devices.limit')
                .replace('{used}', String(devices.data.used))
                .replace('{limit}', String(devices.data.limit))}
        </p>

        {unlink.error === null ? null : (
          <p role="alert" className="mt-3 text-sm text-danger">
            {mutationErrorText(unlink.error, language)}
          </p>
        )}

        {devices.data === undefined || devices.data.devices.length === 0 ? (
          <EmptyState className="mt-4" title={translate(language, 'devices.empty')} />
        ) : (
          <ul className="mt-4 divide-y divide-border-subtle">
            {devices.data.devices.map((device) => {
              const name = deviceName(device, language)
              return (
                <li
                  key={device.hwid}
                  className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-text">{name}</p>
                    <p className="mt-1 truncate text-sm text-text-secondary">
                      {[device.platform, device.os_version].filter(Boolean).join(' · ') ||
                        translate(language, 'devices.unknown_platform')}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="shrink-0"
                    aria-label={`${translate(language, 'devices.unlink')} ${name}`}
                    onClick={() => setPending(device)}
                    disabled={unlink.isPending}
                  >
                    {translate(language, 'devices.unlink')}
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </Card>

      <Dialog
        open={pending !== null}
        onClose={() => setPending(null)}
        title={translate(language, 'devices.unlink_confirm')}
        description={
          language === 'ru'
            ? 'Доступ на этом устройстве прекратится.'
            : 'Access on this device will stop.'
        }
      >
        <Button type="button" variant="secondary" onClick={() => setPending(null)}>
          {translate(language, 'common.cancel')}
        </Button>
        <Button type="button" onClick={confirmUnlink}>
          {translate(language, 'devices.unlink')}
        </Button>
      </Dialog>
    </main>
  )
}

export const devicesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/devices',
  component: Devices,
})
