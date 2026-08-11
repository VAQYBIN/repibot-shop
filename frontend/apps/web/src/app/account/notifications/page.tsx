'use client'

import { useNotificationSettings, useUpdateNotificationSettings } from '@repibot/core'
import { Card, Switch } from '@repibot/ui'

import { errorText, useProfileLanguage, useTranslate } from '@/lib/i18n'

export default function NotificationsPage() {
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const settings = useNotificationSettings()
  const update = useUpdateNotificationSettings(language)

  // Пока ответа нет, переключатель показывать нечем: значение по умолчанию
  // соврало бы отписавшемуся, что новости ему всё ещё приходят.
  const enabled = settings.data?.marketing_enabled

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{t('notifications.title')}</h1>

      <Card>
        {settings.isPending ? (
          <p className="text-text-secondary">{t('common.loading')}</p>
        ) : enabled === undefined ? (
          <p role="alert" className="text-sm text-danger">
            {t('common.error')}
          </p>
        ) : (
          <>
            <Switch
              id="marketing"
              checked={enabled}
              disabled={update.isPending}
              label={t('notifications.marketing')}
              onCheckedChange={(checked) => update.mutate(checked)}
            />
            <p className="mt-2 text-sm text-text-secondary">{t('notifications.marketing_hint')}</p>
            {/* Подсказка обязательна: без неё отписка читается как отказ от
                всех уведомлений, включая оплату и окончание подписки. */}
            <p className="mt-4 text-sm text-text-muted">{t('notifications.service_hint')}</p>
          </>
        )}

        {update.error === null ? null : (
          <p role="alert" className="mt-4 text-sm text-danger">
            {errorText(update.error, language)}
          </p>
        )}
      </Card>
    </div>
  )
}
