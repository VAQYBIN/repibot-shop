'use client'

import { registerSchema, useAuthClient, useRegister } from '@repibot/core'
import { Button, FormField, Input, PasswordInput } from '@repibot/ui'
import { useMutation } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { useState } from 'react'

import { errorText, useBrowserLanguage, useTranslate } from '@/lib/i18n'

export default function RegisterPage() {
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const { api } = useAuthClient()
  const register = useRegister(language)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  // Повторное письмо шлётся тем же публичным эндпоинтом, что и после
  // истечения ссылки: отдельного состояния «письмо ушло» на бэкенде нет.
  const resend = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST('/api/auth/resend-verification', { body: { email } })
      if (error) throw error
    },
  })

  async function submit(event: FormEvent) {
    event.preventDefault()
    setFormError(null)

    const parsed = registerSchema.safeParse({ email, password, language })
    if (!parsed.success) {
      // Сообщения zod английские и не переводятся: показываем свои фразы,
      // а от разбора берём только то, какое поле не прошло.
      const fields = parsed.error.flatten().fieldErrors
      setEmailError(fields.email === undefined ? null : t('auth.error.email_invalid'))
      setPasswordError(fields.password === undefined ? null : t('auth.error.weak_password'))
      return
    }

    setEmailError(null)
    setPasswordError(null)
    try {
      await register.mutateAsync(parsed.data)
      setDone(true)
    } catch (error) {
      setFormError(errorText(error, language))
    }
  }

  if (done) {
    return (
      <div className="flex w-full flex-col gap-4">
        <h1 className="text-2xl font-semibold text-text">{t('auth.verify.title')}</h1>
        <p className="text-text-secondary">{t('auth.verify.pending')}</p>
        <Button
          type="button"
          variant="secondary"
          disabled={resend.isPending || resend.isSuccess}
          onClick={() => resend.mutate()}
        >
          {resend.isSuccess ? t('auth.verify.resent') : t('auth.verify.resend')}
        </Button>
        {resend.error === null ? null : (
          <p role="alert" className="text-sm text-danger">
            {errorText(resend.error, language)}
          </p>
        )}
      </div>
    )
  }

  return (
    <form onSubmit={submit} noValidate className="flex w-full flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{t('auth.register.title')}</h1>

      <FormField label={t('auth.field.email')} htmlFor="email" error={emailError}>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </FormField>

      <FormField
        label={t('auth.field.password')}
        htmlFor="password"
        hint={t('auth.hint.password')}
        error={passwordError}
      >
        <PasswordInput
          id="password"
          autoComplete="new-password"
          showLabel={t('auth.field.password_show')}
          hideLabel={t('auth.field.password_hide')}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </FormField>

      {formError === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {formError}
        </p>
      )}

      <Button type="submit" disabled={register.isPending}>
        {register.isPending ? t('auth.register.pending') : t('auth.register.submit')}
      </Button>

      <a href="/login" className="text-sm text-text-accent hover:underline">
        {t('auth.register.login_link')}
      </a>
    </form>
  )
}
