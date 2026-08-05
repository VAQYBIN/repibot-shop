'use client'

import { resetSchema, useAuthClient } from '@repibot/core'
import { Button, FormField, PasswordInput } from '@repibot/ui'
import { useMutation } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import type { FormEvent } from 'react'
import { useState } from 'react'

import { errorText, useBrowserLanguage, useTranslate } from '@/lib/i18n'
import { useQueryParam } from '@/lib/query-param'

export default function ResetPasswordPage() {
  const router = useRouter()
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const { api } = useAuthClient()
  const token = useQueryParam('token')
  const [password, setPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)

  const reset = useMutation({
    mutationFn: async (input: { token: string; password: string }) => {
      const { error } = await api.POST('/api/auth/password/reset', { body: input })
      if (error) throw error
    },
    // Сброс выдаёт сессию вместе с refresh-cookie, поэтому вести на форму
    // входа было бы лишним шагом.
    onSuccess: () => router.replace('/account'),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    const parsed = resetSchema.safeParse({ token: token ?? '', password })
    if (!parsed.success) {
      const fields = parsed.error.flatten().fieldErrors
      setPasswordError(
        fields.token === undefined ? t('auth.error.weak_password') : t('auth.reset.no_token'),
      )
      return
    }
    setPasswordError(null)
    reset.mutate(parsed.data)
  }

  return (
    <form onSubmit={submit} noValidate className="flex w-full flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{t('auth.reset.title')}</h1>

      <FormField
        label={t('auth.field.new_password')}
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

      {reset.error === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {errorText(reset.error, language)}
        </p>
      )}

      <Button type="submit" disabled={reset.isPending || token === undefined}>
        {t('auth.reset.submit')}
      </Button>
    </form>
  )
}
