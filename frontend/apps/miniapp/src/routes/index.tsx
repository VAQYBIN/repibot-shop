import { translate, useMe } from '@repibot/core'
import { Card } from '@repibot/ui'
import { createRoute } from '@tanstack/react-router'

import { useLanguage } from '../api'
import { useAuthState } from '../auth'
import { AuthFallback, Loading, Retry } from '../auth-fallback'
import { rootRoute } from './root'

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
      <h1 className="text-h1 font-semibold">{name ? `${welcome}, ${name}` : welcome}</h1>
      <p className="mt-2 text-text-secondary">{translate(language, 'home.subtitle')}</p>
    </Card>
  )
}

export function Home() {
  const state = useAuthState((store) => store.state)

  if (state === 'ready') return <Welcome />
  return <AuthFallback state={state} />
}

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: Home,
})
