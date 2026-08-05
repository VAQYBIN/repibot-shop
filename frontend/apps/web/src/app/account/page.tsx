'use client'

import { type Language, useMe, useUpdateProfile } from '@repibot/core'
import { Button, Card, FormField, Input } from '@repibot/ui'
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

  if (me.isPending) return <p className="text-text-secondary">{t('common.loading')}</p>
  if (me.data === undefined) return <p role="alert">{t('common.error')}</p>

  function submit(event: FormEvent) {
    event.preventDefault()
    // Пустое имя — это отсутствие имени, а не пустая строка: бэкенд хранит null.
    update.mutate({ name: name.trim() === '' ? null : name.trim(), language: chosen })
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{t('account.title')}</h1>

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
            <select
              id="language"
              value={chosen}
              onChange={(event) => setChosen(event.target.value as Language)}
              className="h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-text focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none"
            >
              {LANGUAGES.map((code) => (
                <option key={code} value={code}>
                  {code === 'ru' ? 'Русский' : 'English'}
                </option>
              ))}
            </select>
          </FormField>

          {update.error === null ? null : (
            <p role="alert" className="text-sm text-danger">
              {errorText(update.error, language)}
            </p>
          )}

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={update.isPending}>
              {t('common.save')}
            </Button>
            {update.isSuccess ? (
              <span className="text-sm text-text-secondary">{t('account.saved')}</span>
            ) : null}
          </div>
        </form>
      </Card>

      <Card>
        <dl className="flex flex-col gap-3 text-sm">
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
    </div>
  )
}
