'use client'

import {
  emailSchema,
  passwordSchema,
  useAuthClient,
  useMe,
  useRequestEmailChange,
  useRevokeSession,
  useSessions,
} from '@repibot/core'
import { Button, Card, Dialog, EmptyState, FormField, Input, PasswordInput } from '@repibot/ui'
import { useMutation } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { useState } from 'react'

import { errorText, useProfileLanguage, useTranslate } from '@/lib/i18n'
import { passkeyErrorText, useAddPasskey, useDeletePasskey, usePasskeys } from '@/lib/passkey'
import { useLinkCode, useUnlinkTelegram } from '@/lib/telegram'

export default function SecurityPage() {
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const me = useMe()
  const { api } = useAuthClient()
  const sessions = useSessions()
  const revoke = useRevokeSession(language)
  const requestEmail = useRequestEmailChange(language)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [pendingRevoke, setPendingRevoke] = useState<string | null>(null)
  const passkeys = usePasskeys()
  const addPasskey = useAddPasskey()
  const deletePasskey = useDeletePasskey()
  const [keyName, setKeyName] = useState('')
  const [pendingKey, setPendingKey] = useState<number | null>(null)
  const linkCode = useLinkCode(language)
  const unlink = useUnlinkTelegram(language)
  const [unlinkOpen, setUnlinkOpen] = useState(false)

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
  // Почты тоже может не быть — у пришедшего из Telegram. Форма та же, меняются
  // только подписи: там, где адреса нет, речь идёт о его добавлении.
  const hasEmail = me.data?.email != null

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

  function submitEmail(event: FormEvent) {
    event.preventDefault()
    const parsed = emailSchema.safeParse({ email })
    if (!parsed.success) {
      setEmailError(t('auth.error.email_invalid'))
      return
    }
    setEmailError(null)
    // Поле очищается после отправки: адрес уже уехал в письмо, а оставленное
    // значение выглядело бы как несохранённая правка.
    requestEmail.mutate(parsed.data.email, { onSuccess: () => setEmail('') })
  }

  function submitPasskey(event: FormEvent) {
    event.preventDefault()
    addPasskey.mutate(keyName.trim(), { onSuccess: () => setKeyName('') })
  }

  // Отмена окна выбора ключа приходит сюда наравне с отказом сервера, но
  // фразы у неё нет: человек закрыл окно сам, объяснять ему нечего.
  const passkeyFailure = addPasskey.error ?? deletePasskey.error
  const passkeyError = passkeyFailure === null ? null : passkeyErrorText(passkeyFailure, language)

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
        {/* Подписи зависят от того, есть ли адрес, поэтому карточка ждёт
            профиль: иначе первый кадр звал бы менять несуществующую почту. */}
        {me.isPending ? (
          <p className="text-text-secondary">{t('common.loading')}</p>
        ) : (
          <>
            <h2 className="text-lg font-semibold text-text">
              {hasEmail ? t('account.email_change') : t('account.email_add')}
            </h2>
            <form onSubmit={submitEmail} noValidate className="mt-4 flex flex-col gap-4">
              <FormField
                label={hasEmail ? t('account.email_new') : t('account.email')}
                htmlFor="new-email"
                hint={t('account.email_change_hint')}
                error={emailError}
              >
                <Input
                  id="new-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </FormField>

              {requestEmail.error === null ? null : (
                <p role="alert" className="text-sm text-danger">
                  {errorText(requestEmail.error, language)}
                </p>
              )}

              <div className="flex items-center gap-3">
                <Button type="submit" disabled={requestEmail.isPending}>
                  {t('account.email_change_submit')}
                </Button>
                {requestEmail.isSuccess ? (
                  <span className="text-sm text-text-secondary">
                    {t('account.email_change_sent')}
                  </span>
                ) : null}
              </div>
            </form>
          </>
        )}
      </Card>

      <Card>
        <h2 className="text-lg font-semibold text-text">{t('account.passkeys.title')}</h2>
        <p className="mt-1 text-sm text-text-secondary">{t('account.passkeys.hint')}</p>

        {passkeyError === null ? null : (
          <p role="alert" className="mt-2 text-sm text-danger">
            {passkeyError}
          </p>
        )}

        {passkeys.isPending ? (
          <p className="mt-4 text-text-secondary">{t('common.loading')}</p>
        ) : passkeys.data === undefined || passkeys.data.length === 0 ? (
          <EmptyState className="mt-4" title={t('account.passkeys.empty')} />
        ) : (
          <ul className="mt-4 flex flex-col gap-3">
            {passkeys.data.map((key) => (
              <li key={key.id} className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="truncate text-sm text-text">{key.name}</p>
                  <p className="text-sm text-text-muted">
                    {key.last_used_at === null
                      ? t('account.passkeys.never_used')
                      : `${t('account.passkeys.last_used')}: ${new Date(
                          key.last_used_at,
                        ).toLocaleString(language)}`}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setPendingKey(key.id)}
                >
                  {t('account.passkeys.delete')}
                </Button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={submitPasskey} noValidate className="mt-4 flex flex-col gap-4">
          <FormField label={t('account.passkeys.name')} htmlFor="passkey-name">
            <Input
              id="passkey-name"
              value={keyName}
              placeholder={t('account.passkeys.name_placeholder')}
              onChange={(event) => setKeyName(event.target.value)}
            />
          </FormField>
          <div>
            <Button type="submit" disabled={addPasskey.isPending}>
              {addPasskey.isPending ? t('account.passkeys.adding') : t('account.passkeys.add')}
            </Button>
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

        {me.data?.has_telegram === true ? (
          <>
            <p className="mt-2 text-sm text-text-secondary">
              {me.data.telegram_username === null
                ? t('account.telegram_linked')
                : `@${me.data.telegram_username}`}
            </p>
            {unlink.error === null ? null : (
              <p role="alert" className="mt-2 text-sm text-danger">
                {errorText(unlink.error, language)}
              </p>
            )}
            <div className="mt-4">
              <Button type="button" variant="secondary" onClick={() => setUnlinkOpen(true)}>
                {t('account.telegram.unlink')}
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="mt-2 text-sm text-text-secondary">{t('account.telegram_absent')}</p>
            {linkCode.data === undefined ? (
              <div className="mt-4">
                <Button
                  type="button"
                  onClick={() => linkCode.mutate()}
                  disabled={linkCode.isPending}
                >
                  {t('account.telegram.link')}
                </Button>
              </div>
            ) : (
              <div className="mt-4 flex flex-col gap-3">
                <p className="text-sm text-text-secondary">{t('account.telegram.code_hint')}</p>
                {/* Код набирают руками в чате бота: моноширинный шрифт и
                    разрядка нужны, чтобы не спутать похожие знаки. */}
                <p className="font-mono text-2xl tracking-widest text-text">{linkCode.data.code}</p>
                <p className="text-sm text-text-muted">{t('account.telegram.code_expires')}</p>
                <div>
                  {/* Ссылка, а не window.open: чужой домен должен быть виден
                      до перехода и открываться средствами браузера. */}
                  <Button asChild>
                    <a href={linkCode.data.url} target="_blank" rel="noopener noreferrer">
                      {t('account.telegram.open_bot')}
                    </a>
                  </Button>
                </div>
              </div>
            )}
            {linkCode.error === null ? null : (
              <p role="alert" className="mt-2 text-sm text-danger">
                {errorText(linkCode.error, language)}
              </p>
            )}
          </>
        )}
      </Card>

      <Dialog
        open={pendingKey !== null}
        onClose={() => setPendingKey(null)}
        title={t('account.passkeys.delete_title')}
        description={t('account.passkeys.delete_text')}
      >
        <Button type="button" variant="secondary" onClick={() => setPendingKey(null)}>
          {t('common.cancel')}
        </Button>
        <Button
          type="button"
          onClick={() => {
            if (pendingKey !== null) deletePasskey.mutate(pendingKey)
            setPendingKey(null)
          }}
        >
          {t('account.passkeys.delete')}
        </Button>
      </Dialog>

      <Dialog
        open={unlinkOpen}
        onClose={() => setUnlinkOpen(false)}
        title={t('account.telegram.unlink_title')}
        description={t('account.telegram.unlink_text')}
      >
        <Button type="button" variant="secondary" onClick={() => setUnlinkOpen(false)}>
          {t('common.cancel')}
        </Button>
        <Button
          type="button"
          onClick={() => {
            unlink.mutate()
            setUnlinkOpen(false)
          }}
        >
          {t('account.telegram.unlink')}
        </Button>
      </Dialog>

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
