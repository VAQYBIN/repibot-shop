'use client'

import { type Language, useMe, useUpdateProfile } from '@repibot/core'
import { Alert, Button, Card, FormField, Input, Select, Spinner } from '@repibot/ui'
import type { FormEvent } from 'react'
import { useEffect, useState } from 'react'

import { errorText, useProfileLanguage, useTranslate } from '@/lib/i18n'

const LANGUAGES: readonly Language[] = ['ru', 'en']

export default function AccountPage() {
  const me = useMe()
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const update = useUpdateProfile(language)
  const [name, setName] = useState('')
  const [chosen, setChosen] = useState<Language>(language)

  // Профиль приезжает асинхронно, поэтому поля наполняются после ответа.
  // Зависимость — сами данные: пока их нет, редактировать нечего.
  useEffect(() => {
    if (me.data === undefined) return
    setName(me.data.name ?? '')
    setChosen(me.data.language)
  }, [me.data])

  if (me.isPending) return <Spinner label={t('common.loading')} />
  if (me.data === undefined) return <Alert tone="error">{t('common.error')}</Alert>

  function submit(event: FormEvent) {
    event.preventDefault()
    // Пустое имя — это отсутствие имени, а не пустая строка: бэкенд хранит null.
    update.mutate({ name: name.trim() === '' ? null : name.trim(), language: chosen })
  }

  return (
    <main className="flex flex-col gap-6">
      <h1 className="text-h1 font-semibold text-text">{t('account.title')}</h1>

      <Card>
        <form onSubmit={submit} noValidate className="flex flex-col gap-4">
          <FormField label={t('account.name')} htmlFor="name">
            <Input
              id="name"
              autoComplete="name"
              placeholder={t('account.name_empty')}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </FormField>

          <FormField label={t('account.language')} htmlFor="language">
            <Select
              id="language"
              value={chosen}
              onChange={(event) => setChosen(event.target.value as Language)}
            >
              {LANGUAGES.map((code) => (
                <option key={code} value={code}>
                  {code === 'ru' ? 'Русский' : 'English'}
                </option>
              ))}
            </Select>
          </FormField>

          {update.error === null ? null : (
            <Alert tone="error">{errorText(update.error, language)}</Alert>
          )}

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={update.isPending}>
              {t('common.save')}
            </Button>
            {update.isSuccess ? (
              <span className="text-small text-text-secondary">{t('account.saved')}</span>
            ) : null}
          </div>
        </form>
      </Card>

      <Card>
        <dl className="flex flex-col gap-3 text-small">
          <div className="flex justify-between gap-4">
            <dt className="text-text-secondary">{t('account.email')}</dt>
            <dd className="flex flex-col items-end gap-1 text-text">
              <span>{me.data.email ?? '—'}</span>
              <span className={me.data.email_verified ? 'text-success' : 'text-warning'}>
                {me.data.email_verified
                  ? t('account.email_verified')
                  : t('account.email_unverified')}
              </span>
            </dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-text-secondary">{t('account.referral_code')}</dt>
            <dd className="font-mono text-text">{me.data.referral_code}</dd>
          </div>
        </dl>
      </Card>
    </main>
  )
}
