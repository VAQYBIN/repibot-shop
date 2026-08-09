'use client'

import { type Language, translate, useDevices, useUnlinkDevice } from '@repibot/core'
import { Button, Card, Dialog, EmptyState } from '@repibot/ui'
import { useState } from 'react'

import { errorText } from '@/lib/i18n'

interface DeviceListProps {
  language: Language
}

interface Device {
  hwid: string
  platform: string | null
  device_model: string | null
  os_version: string | null
  created_at: string
}

function deviceName(device: Device, language: Language): string {
  return device.device_model ?? device.platform ?? translate(language, 'devices.unknown_platform')
}

export function DeviceList({ language }: DeviceListProps) {
  const devices = useDevices()
  const unlink = useUnlinkDevice(language)
  const [pending, setPending] = useState<Device | null>(null)

  function confirmUnlink() {
    if (pending === null) return
    unlink.mutate(pending.hwid)
    setPending(null)
  }

  return (
    <>
      <Card role="region" aria-labelledby="devices-title">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="devices-title" className="text-lg font-semibold text-text">
            {translate(language, 'devices.title')}
          </h2>
          {devices.data === undefined ? null : (
            <p className="text-sm tabular-nums text-text-secondary">
              {translate(language, 'devices.limit')
                .replace('{used}', String(devices.data.used))
                .replace('{limit}', String(devices.data.limit))}
            </p>
          )}
        </div>

        {unlink.error === null ? null : (
          <p role="alert" className="mt-3 text-sm text-danger">
            {errorText(unlink.error, language)}
          </p>
        )}

        {devices.isPending ? (
          <p role="status" className="mt-4 text-sm text-text-secondary">
            {translate(language, 'common.loading')}
          </p>
        ) : devices.error !== null ? (
          <p role="alert" className="mt-4 text-sm text-danger">
            {errorText(devices.error, language)}
          </p>
        ) : devices.data === undefined || devices.data.devices.length === 0 ? (
          <EmptyState className="mt-4" title={translate(language, 'devices.empty')} />
        ) : (
          <ul className="mt-4 divide-y divide-border-subtle">
            {devices.data.devices.map((device) => {
              const name = deviceName(device, language)
              return (
                <li
                  key={device.hwid}
                  className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-text">{name}</p>
                    <p className="mt-1 text-sm text-text-secondary">
                      {[device.platform, device.os_version].filter(Boolean).join(' · ') ||
                        translate(language, 'devices.unknown_platform')}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
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
    </>
  )
}
