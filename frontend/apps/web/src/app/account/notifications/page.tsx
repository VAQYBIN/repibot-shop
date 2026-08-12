'use client'

import { useNotificationSettings, useUpdateNotificationSettings } from '@repibot/core'
import { Alert, Card, Spinner, Switch } from '@repibot/ui'

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
    <main className="flex flex-col gap-6">
      <h1 className="text-h1 font-semibold text-text">{t('notifications.title')}</h1>

      <Card>
        {settings.isPending ? (
          <Spinner label={t('common.loading')} />
        ) : enabled === undefined ? (
          <Alert tone="error">{t('common.error')}</Alert>
        ) : (
          <>
            <Switch
              id="marketing"
              checked={enabled}
              disabled={update.isPending}
              label={t('notifications.marketing')}
              onCheckedChange={(checked) => update.mutate(checked)}
            />
            <p className="mt-2 text-small text-text-secondary">
              {t('notifications.marketing_hint')}
            </p>
            {/* Подсказка обязательна: без неё отписка читается как отказ от
                всех уведомлений, включая оплату и окончание подписки. Отдельный
                абзац с отступом отделяет её от переключателей — это подпись,
                а не текст наравне с остальным. */}
            <p className="mt-4 text-caption text-text-muted">{t('notifications.service_hint')}</p>
          </>
        )}

        {update.error === null ? null : (
          <Alert tone="error" className="mt-4">
            {errorText(update.error, language)}
          </Alert>
        )}
      </Card>
    </main>
  )
}
