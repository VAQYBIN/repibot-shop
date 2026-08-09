import { type Language, translate, useMe, useUpdateProfile } from '@repibot/core'
import { Button, Card } from '@repibot/ui'
import { createRoute } from '@tanstack/react-router'

import { useLanguage } from '../api'
import { Loading, Retry } from '../auth-fallback'
import { rootRoute } from './root'

/** Язык подписывается на своём языке: перевод названия читателю не помогает. */
const LANGUAGE_NAMES: Record<Language, string> = { ru: 'Русский', en: 'English' }
const LANGUAGES: readonly Language[] = ['ru', 'en']

export function Profile() {
  const language = useLanguage()
  const profile = useMe()
  const save = useUpdateProfile(language)

  if (profile.isPending) return <Loading language={language} />
  if (profile.data === undefined) {
    return (
      <Retry
        language={language}
        message={translate(language, 'common.error')}
        onRetry={() => void profile.refetch()}
      />
    )
  }

  const me = profile.data

  return (
    <Card className="mx-auto max-w-md">
      <h1 className="text-2xl font-semibold">{translate(language, 'account.title')}</h1>

      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <dt className="text-text-secondary">{translate(language, 'account.name')}</dt>
        <dd className="text-text">{me.name ?? me.telegram_username ?? '—'}</dd>
        <dt className="text-text-secondary">{translate(language, 'account.referral_code')}</dt>
        <dd className="font-mono text-text">{me.referral_code}</dd>
      </dl>

      <section className="mt-6">
        <h2 className="text-sm text-text-secondary">{translate(language, 'account.language')}</h2>
        <div className="mt-2 flex gap-2">
          {LANGUAGES.map((option) => (
            <Button
              key={option}
              size="sm"
              variant={option === language ? 'primary' : 'secondary'}
              aria-pressed={option === language}
              disabled={save.isPending}
              // Имя отправляется вместе с языком: PATCH заменяет профиль
              // целиком, и без него сервер стёр бы его в null.
              onClick={() => save.mutate({ name: me.name, language: option })}
            >
              {LANGUAGE_NAMES[option]}
            </Button>
          ))}
        </div>
      </section>

      {save.isError && (
        <p className="mt-4 text-sm text-text" role="alert">
          {translate(language, 'common.error')}
        </p>
      )}
    </Card>
  )
}

export const profileRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/profile',
  component: Profile,
})
