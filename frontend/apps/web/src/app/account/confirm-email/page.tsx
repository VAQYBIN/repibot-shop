'use client'

import { useAuthClient } from '@repibot/core'
import { Card } from '@repibot/ui'
import { useEffect, useRef, useState } from 'react'

import { errorText, useProfileLanguage, useTranslate } from '@/lib/i18n'
import { useQueryParam } from '@/lib/query-param'

export default function ConfirmEmailPage() {
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const { api } = useAuthClient()
  const token = useQueryParam('token')
  const [state, setState] = useState<'checking' | 'done' | 'failed'>('checking')
  const [failure, setFailure] = useState<string | null>(null)
  // Токен одноразовый: повторный вызов из-за двойного эффекта в разработке
  // сжёг бы живую ссылку.
  const asked = useRef(false)

  useEffect(() => {
    if (token === undefined || asked.current) return
    asked.current = true

    if (token === null) {
      setFailure(t('auth.error.token_invalid'))
      setState('failed')
      return
    }

    void api.POST('/api/auth/email/change-confirm', { body: { token } }).then(({ error }) => {
      if (error === undefined) {
        setState('done')
        return
      }
      setFailure(errorText(error, language))
      setState('failed')
    })
  }, [api, language, t, token])

  return (
    <Card>
      <h1 className="text-2xl font-semibold text-text">{t('account.confirm_email.title')}</h1>
      {state === 'checking' ? (
        <p className="mt-2 text-text-secondary">{t('auth.verify.checking')}</p>
      ) : null}
      {state === 'done' ? (
        <p className="mt-2 text-text-secondary">{t('account.confirm_email.done')}</p>
      ) : null}
      {state === 'failed' ? (
        <p role="alert" className="mt-2 text-sm text-danger">
          {failure}
        </p>
      ) : null}
    </Card>
  )
}
