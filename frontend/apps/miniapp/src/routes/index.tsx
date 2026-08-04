import { translate } from '@repibot/core'
import { Card } from '@repibot/ui'
import { createRoute } from '@tanstack/react-router'

import { isInsideTelegram } from '../telegram'
import { rootRoute } from './root'

export function Home() {
  return (
    <Card className="mx-auto max-w-md">
      <h1 className="text-2xl font-semibold">{translate('ru', 'home.title')}</h1>
      <p className="mt-2 text-text-secondary">{translate('ru', 'home.subtitle')}</p>
      <p className="mt-4 font-mono text-sm text-text-muted">
        {isInsideTelegram() ? 'Telegram: подключён' : 'Telegram: вне приложения'}
      </p>
    </Card>
  )
}

export const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: Home,
})
