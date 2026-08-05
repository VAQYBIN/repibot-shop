'use client'

import { loginSchema, useLogin } from '@repibot/core'
import { Button, FormField, Input, PasswordInput } from '@repibot/ui'
import { useRouter } from 'next/navigation'
import type { FormEvent } from 'react'
import { useState } from 'react'

import { useBrowserLanguage, useTranslate } from '@/lib/i18n'

export default function LoginPage() {
  const router = useRouter()
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const login = useLogin(language)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setFormError(null)

    // Проверка на клиенте — чтобы не гонять заведомо неверные данные; на
    // бэкенде те же правила проверяются заново, клиенту доверия нет.
    const parsed = loginSchema.safeParse({ email, password })
    if (!parsed.success) {
      setFormError(t('auth.error.form'))
      return
    }

    try {
      await login.mutateAsync(parsed.data)
      // Токен намеренно не сохраняется здесь: в кабинете AuthGuard обновит его
      // по cookie, и это единственный путь его получения.
      router.replace('/account')
    } catch (error) {
      setFormError(error instanceof Error ? error.message : t('auth.error.unknown'))
    }
  }

  // noValidate: встроенная проверка браузера показывает подсказки на своём
  // языке и не даёт форме отправиться, поэтому наше сообщение до пользователя
  // не доходит. Единственный источник правды о форме — zod.
  return (
    <form onSubmit={submit} noValidate className="flex w-full flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{t('auth.login.title')}</h1>

      <FormField label={t('auth.field.email')} htmlFor="email">
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </FormField>

      <FormField label={t('auth.field.password')} htmlFor="password">
        <PasswordInput
          id="password"
          autoComplete="current-password"
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

      <Button type="submit" disabled={login.isPending}>
        {login.isPending ? t('auth.login.pending') : t('auth.login.submit')}
      </Button>

      <div className="flex justify-between text-sm">
        <a href="/register" className="text-text-accent hover:underline">
          {t('auth.login.register_link')}
        </a>
        <a href="/forgot-password" className="text-text-accent hover:underline">
          {t('auth.login.forgot_link')}
        </a>
      </div>

      {/* Кнопка появится в плане 1b вместе с OIDC. Показываем отключённой, чтобы
          вход через Telegram не выглядел отсутствующим в продукте. */}
      <Button type="button" variant="secondary" disabled>
        {t('auth.login.telegram_soon')}
      </Button>
    </form>
  )
}
