'use client'

import { emailSchema, useAuthClient } from '@repibot/core'
import { Alert, Button, FormField, Input, Spinner } from '@repibot/ui'
import { useMutation } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import type { FormEvent } from 'react'
import { useEffect, useRef, useState } from 'react'

import { errorText, useBrowserLanguage, useTranslate } from '@/lib/i18n'
import { useQueryParam } from '@/lib/query-param'

export default function VerifyEmailPage() {
  const router = useRouter()
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const { api } = useAuthClient()
  const token = useQueryParam('token')
  const [failure, setFailure] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  // Ссылка одноразовая: повторный вызов из-за двойного эффекта в разработке
  // сжёг бы токен и показал бы ошибку на живой ссылке.
  const asked = useRef(false)

  const resend = useMutation({
    mutationFn: async (address: string) => {
      const { error } = await api.POST('/api/auth/resend-verification', {
        body: { email: address },
      })
      if (error) throw error
    },
  })

  useEffect(() => {
    if (token === undefined || asked.current) return
    asked.current = true

    if (token === null) {
      setFailure(t('auth.error.token_invalid'))
      return
    }

    void api.POST('/api/auth/verify-email', { body: { token } }).then(({ error }) => {
      // Ответ несёт refresh-cookie, поэтому в кабинете гейт сразу получит токен.
      if (error === undefined) router.replace('/account')
      else setFailure(errorText(error, language))
    })
  }, [api, language, router, t, token])

  function submitResend(event: FormEvent) {
    event.preventDefault()
    const parsed = emailSchema.safeParse({ email })
    if (!parsed.success) {
      setEmailError(t('auth.error.email_invalid'))
      return
    }
    setEmailError(null)
    resend.mutate(parsed.data.email)
  }

  if (failure === null) {
    return (
      <div className="flex w-full flex-col gap-4">
        <h1 className="text-h1 font-semibold text-text">{t('auth.verify.title')}</h1>
        <Spinner label={t('auth.verify.checking')} />
      </div>
    )
  }

  return (
    <form onSubmit={submitResend} noValidate className="flex w-full flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">{t('auth.verify.title')}</h1>
      <Alert tone="error">{failure}</Alert>

      <FormField label={t('auth.field.email')} htmlFor="email" error={emailError}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </FormField>

      <Button type="submit" disabled={resend.isPending || resend.isSuccess}>
        {resend.isSuccess ? t('auth.verify.resent') : t('auth.verify.resend')}
      </Button>

      <a href="/login" className="text-small text-text-accent hover:underline">
        {t('auth.forgot.back_link')}
      </a>
    </form>
  )
}
