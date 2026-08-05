'use client'

import { passwordSchema, useAuthClient, useMe, useRevokeSession, useSessions } from '@repibot/core'
import { Button, Card, Dialog, EmptyState, FormField, PasswordInput } from '@repibot/ui'
import { useMutation } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { useState } from 'react'

import { errorText, useProfileLanguage, useTranslate } from '@/lib/i18n'

export default function SecurityPage() {
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const me = useMe()
  const { api } = useAuthClient()
  const sessions = useSessions()
  const revoke = useRevokeSession(language)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [pendingRevoke, setPendingRevoke] = useState<string | null>(null)

  const changePassword = useMutation({
    mutationFn: async (input: { current_password: string | null; new_password: string }) => {
      const { error } = await api.POST('/api/me/password', { body: input })
      if (error) throw error
    },
    onSuccess: () => {
      setCurrent('')
      setNext('')
    },
  })

  // Пароля может не быть вовсе: аккаунт мог появиться из Telegram. Тогда
  // текущий пароль спрашивать не у чего.
  const hasPassword = me.data?.has_password ?? true

  function submitPassword(event: FormEvent) {
    event.preventDefault()
    const parsed = passwordSchema.safeParse({ password: next })
    if (!parsed.success) {
      setPasswordError(t('auth.error.weak_password'))
      return
    }
    setPasswordError(null)
    changePassword.mutate({
      current_password: hasPassword ? current : null,
      new_password: parsed.data.password,
    })
  }

  function confirmRevoke() {
    if (pendingRevoke === null) return
    revoke.mutate(pendingRevoke)
    setPendingRevoke(null)
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold text-text">{t('account.security')}</h1>

      <Card>
        <h2 className="text-lg font-semibold text-text">{t('account.password_change')}</h2>
        <form onSubmit={submitPassword} noValidate className="mt-4 flex flex-col gap-4">
          {hasPassword ? (
            <FormField label={t('auth.field.current_password')} htmlFor="current-password">
              <PasswordInput
                id="current-password"
                autoComplete="current-password"
                showLabel={t('auth.field.password_show')}
                hideLabel={t('auth.field.password_hide')}
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
              />
            </FormField>
          ) : null}

          <FormField
            label={t('auth.field.new_password')}
            htmlFor="new-password"
            hint={t('auth.hint.password')}
            error={passwordError}
          >
            <PasswordInput
              id="new-password"
              autoComplete="new-password"
              showLabel={t('auth.field.password_show')}
              hideLabel={t('auth.field.password_hide')}
              value={next}
              onChange={(event) => setNext(event.target.value)}
            />
          </FormField>

          {changePassword.error === null ? null : (
            <p role="alert" className="text-sm text-danger">
              {errorText(changePassword.error, language)}
            </p>
          )}

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={changePassword.isPending}>
              {t('common.save')}
            </Button>
            {changePassword.isSuccess ? (
              <span className="text-sm text-text-secondary">{t('account.password_saved')}</span>
            ) : null}
          </div>
        </form>
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-text">{t('account.sessions')}</h2>
        {revoke.error === null ? null : (
          <p role="alert" className="mt-2 text-sm text-danger">
            {errorText(revoke.error, language)}
          </p>
        )}
        {sessions.isPending ? (
          <p className="mt-4 text-text-secondary">{t('common.loading')}</p>
        ) : sessions.data === undefined || sessions.data.length === 0 ? (
          <EmptyState className="mt-4" title={t('account.sessions_empty')} />
        ) : (
          <ul className="mt-4 flex flex-col gap-3">
            {sessions.data.map((session) => (
              <li key={session.id} className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="truncate text-sm text-text">
                    {session.user_agent ?? t('account.unknown_device')}
                  </p>
                  <p className="text-sm text-text-muted">
                    {session.is_current
                      ? t('account.current_session')
                      : new Date(session.created_at).toLocaleString(language)}
                  </p>
                </div>
                {session.is_current ? null : (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setPendingRevoke(session.id)}
                  >
                    {t('account.revoke')}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-text">{t('account.telegram')}</h2>
        {/* Привязка и отвязка появятся в плане 1b вместе с OIDC: сейчас
            показываем только текущее состояние. */}
        <p className="mt-2 text-sm text-text-secondary">
          {me.data?.has_telegram === true
            ? t('account.telegram_linked')
            : t('account.telegram_absent')}
        </p>
      </Card>

      <Dialog
        open={pendingRevoke !== null}
        onClose={() => setPendingRevoke(null)}
        title={t('account.revoke_title')}
        description={t('account.revoke_text')}
      >
        <Button type="button" variant="secondary" onClick={() => setPendingRevoke(null)}>
          {t('common.cancel')}
        </Button>
        <Button type="button" onClick={confirmRevoke}>
          {t('account.revoke')}
        </Button>
      </Dialog>
    </div>
  )
}
