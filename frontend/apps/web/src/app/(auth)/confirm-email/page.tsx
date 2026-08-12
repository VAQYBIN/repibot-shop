'use client'

import { useAuthClient } from '@repibot/core'
import { Alert, Spinner } from '@repibot/ui'
import { useEffect, useRef, useState } from 'react'

import { errorText, useBrowserLanguage, useTranslate } from '@/lib/i18n'
import { useQueryParam } from '@/lib/query-param'

/**
 * Подтверждение нового адреса почты.
 *
 * Страница публичная намеренно: письмо открывают в том браузере, где заведена
 * почта, а не в том, где открыт кабинет. Под гейтом кабинета такого человека
 * увело бы на /login, и токен из адреса потерялся бы. Операцию авторизует сам
 * токен — эндпоинт подтверждения тоже публичный.
 *
 * Язык берётся из браузера, а не из профиля: запрашивать профиль здесь не на
 * чем, сессии в этом браузере может не быть вовсе.
 */
export default function ConfirmEmailPage() {
  const language = useBrowserLanguage()
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
    <div className="flex w-full flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">{t('account.confirm_email.title')}</h1>

      {state === 'checking' ? <Spinner label={t('auth.verify.checking')} /> : null}

      {state === 'done' ? (
        <>
          <p className="text-text-secondary">{t('account.confirm_email.done')}</p>
          {/* Две ссылки, потому что неизвестно, есть ли в этом браузере сессия:
              вошедший вернётся в кабинет, остальные войдут новым адресом. */}
          <div className="flex justify-between gap-4 text-small">
            <a href="/login" className="text-text-accent hover:underline">
              {t('account.confirm_email.login_link')}
            </a>
            <a href="/account" className="text-text-accent hover:underline">
              {t('account.confirm_email.account_link')}
            </a>
          </div>
        </>
      ) : null}

      {state === 'failed' ? <Alert tone="error">{failure}</Alert> : null}
    </div>
  )
}
