'use client'

import { errorMessageKey, loginSchema, useLogin } from '@repibot/core'
import { Alert, Button, FormField, Input, PasswordInput } from '@repibot/ui'
import { useRouter } from 'next/navigation'
import type { FormEvent } from 'react'
import { useState } from 'react'

import { useBrowserLanguage, useTranslate } from '@/lib/i18n'
import { passkeyErrorText, usePasskeyLogin } from '@/lib/passkey'
import { useQueryParam } from '@/lib/query-param'
import { useAuthMethods } from '@/lib/telegram'

export default function LoginPage() {
  const router = useRouter()
  const language = useBrowserLanguage()
  const t = useTranslate(language)
  const login = useLogin(language)
  const passkeyLogin = usePasskeyLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const methods = useAuthMethods()
  // Браузерный вход через Telegram отвечает редиректами, включая отказы, и
  // возвращается сюда с кодом ошибки в адресе: показать её иначе цепочка
  // редиректов не может.
  const returnedError = useQueryParam('error')

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

  async function signInWithPasskey() {
    setFormError(null)
    try {
      await passkeyLogin.mutateAsync()
      router.replace('/account')
    } catch (error) {
      // Отмена окна выбора ключа — не повод краснеть: человек просто передумал,
      // и passkeyErrorText отдаёт для неё null.
      const message = passkeyErrorText(error, language)
      if (message !== null) setFormError(message)
    }
  }

  // noValidate: встроенная проверка браузера показывает подсказки на своём
  // языке и не даёт форме отправиться, поэтому наше сообщение до пользователя
  // не доходит. Единственный источник правды о форме — zod.
  return (
    <form onSubmit={submit} noValidate className="flex w-full flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">{t('auth.login.title')}</h1>

      {returnedError === null || returnedError === undefined ? null : (
        <Alert tone="error">{t(errorMessageKey(returnedError))}</Alert>
      )}

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

      {formError === null ? null : <Alert tone="error">{formError}</Alert>}

      <Button type="submit" disabled={login.isPending}>
        {login.isPending ? t('auth.login.pending') : t('auth.login.submit')}
      </Button>

      <div className="flex justify-between text-small">
        <a href="/register" className="text-text-accent hover:underline">
          {t('auth.login.register_link')}
        </a>
        <a href="/forgot-password" className="text-text-accent hover:underline">
          {t('auth.login.forgot_link')}
        </a>
      </div>

      {/* Разделитель отделяет вход по паролю от остальных способов: без него
          четыре кнопки подряд читаются как четыре шага одного пути. */}
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-border-subtle" />
        <span className="text-caption text-text-muted">{language === 'ru' ? 'или' : 'or'}</span>
        <span className="h-px flex-1 bg-border-subtle" />
      </div>

      <div className="flex flex-col gap-3">
        <Button
          type="button"
          variant="secondary"
          onClick={signInWithPasskey}
          disabled={passkeyLogin.isPending}
        >
          {t('auth.login.passkey')}
        </Button>

        {/* Ссылка, а не кнопка с fetch: за ней идёт цепочка редиректов на чужой
            домен, и пройти она должна в адресной строке. Кнопки нет вовсе, пока
            развёртывание не настроено, — она привела бы на страницу с ошибкой. */}
        {methods.data?.telegram === true ? (
          <Button asChild variant="secondary">
            <a href="/api/auth/telegram/start">{t('auth.login.telegram')}</a>
          </Button>
        ) : null}
      </div>
    </form>
  )
}
