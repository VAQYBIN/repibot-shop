import { detectLanguage, type Language, translate, useMe } from '@repibot/core'
import { Button, Card } from '@repibot/ui'
import { createRoute } from '@tanstack/react-router'

import { useLanguage } from '../api'
import { telegramAuthOptions, useAuthState } from '../auth'
import { preferredLanguages } from '../telegram'
import { rootRoute } from './root'

/** Заглушка вместо пустого экрана: вход и профиль занимают по одному запросу. */
export function Loading({ language }: { language: Language }) {
  return (
    <Card className="mx-auto max-w-md" aria-busy="true">
      <p role="status" className="text-text-secondary">
        {translate(language, 'common.loading')}
      </p>
      <div className="mt-4 h-4 animate-pulse rounded-sm bg-surface-sunken" />
      <div className="mt-2 h-4 w-2/3 animate-pulse rounded-sm bg-surface-sunken" />
    </Card>
  )
}

/** Сообщение с кнопкой: тупик без выхода читается как поломка приложения. */
export function Retry({
  language,
  message,
  onRetry,
}: {
  language: Language
  message: string
  onRetry: () => void
}) {
  return (
    <Card className="mx-auto max-w-md">
      <p className="text-text">{message}</p>
      <Button className="mt-4" onClick={onRetry}>
        {translate(language, 'common.retry')}
      </Button>
    </Card>
  )
}

function Welcome() {
  const language = useLanguage()
  const profile = useMe()

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

  const name = profile.data.name ?? profile.data.telegram_username
  const welcome = translate(language, 'miniapp.welcome')

  return (
    <Card className="mx-auto max-w-md">
      <h1 className="text-2xl font-semibold">{name ? `${welcome}, ${name}` : welcome}</h1>
      <p className="mt-2 text-text-secondary">{translate(language, 'home.subtitle')}</p>
    </Card>
  )
}

export function Home() {
  const state = useAuthState((store) => store.state)
  const signIn = useAuthState((store) => store.signIn)
  // До входа язык пользователя взять неоткуда: остаются предпочтения Telegram
  // и браузера.
  const language = detectLanguage(preferredLanguages())

  if (state === 'ready') return <Welcome />
  if (state === 'checking') return <Loading language={language} />
  if (state === 'failed') {
    return (
      <Retry
        language={language}
        message={translate(language, 'miniapp.signin.failed')}
        onRetry={() => void signIn(telegramAuthOptions)}
      />
    )
  }

  return (
    <Card className="mx-auto max-w-md">
      <h1 className="text-2xl font-semibold">{translate(language, 'home.title')}</h1>
      <p className="mt-2 text-text-secondary">{translate(language, 'miniapp.signin.outside')}</p>
    </Card>
  )
}

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: Home,
})
