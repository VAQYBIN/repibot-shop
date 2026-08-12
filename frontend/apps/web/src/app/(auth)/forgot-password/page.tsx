'use client'

import { emailSchema, useAuthClient } from '@repibot/core'
import { Alert, Button, FormField, Input } from '@repibot/ui'
import { useMutation } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { useState } from 'react'

import { errorText, useBrowserLanguage, useTranslate } from '@/lib/i18n'

export default function ForgotPasswordPage() {
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const { api } = useAuthClient()
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)

  const request = useMutation({
    mutationFn: async (address: string) => {
      const { error } = await api.POST('/api/auth/password/forgot', { body: { email: address } })
      if (error) throw error
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    const parsed = emailSchema.safeParse({ email })
    if (!parsed.success) {
      setEmailError(t('auth.error.email_invalid'))
      return
    }
    setEmailError(null)
    request.mutate(parsed.data.email)
  }

  // Ответ один и тот же независимо от того, есть такой адрес или нет: иначе
  // форма превращается в способ проверять чужие адреса на регистрацию.
  if (request.isSuccess) {
    return (
      <div className="flex w-full flex-col gap-4">
        <h1 className="text-h1 font-semibold text-text">{t('auth.forgot.title')}</h1>
        <p className="text-text-secondary">{t('auth.forgot.sent')}</p>
        <a href="/login" className="text-small text-text-accent hover:underline">
          {t('auth.forgot.back_link')}
        </a>
      </div>
    )
  }

  return (
    <form onSubmit={submit} noValidate className="flex w-full flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">{t('auth.forgot.title')}</h1>
      <p className="text-text-secondary">{t('auth.forgot.hint')}</p>

      <FormField label={t('auth.field.email')} htmlFor="email" error={emailError}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </FormField>

      {request.error === null ? null : (
        <Alert tone="error">{errorText(request.error, language)}</Alert>
      )}

      <Button type="submit" disabled={request.isPending}>
        {t('auth.forgot.submit')}
      </Button>

      <a href="/login" className="text-small text-text-accent hover:underline">
        {t('auth.forgot.back_link')}
      </a>
    </form>
  )
}
