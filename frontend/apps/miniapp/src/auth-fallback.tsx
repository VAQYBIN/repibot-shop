import { detectLanguage, type Language, translate } from '@repibot/core'
import { Button, Card } from '@repibot/ui'

import { type AuthState, telegramAuthOptions, useAuthState } from './auth'
import { preferredLanguages } from './telegram'

/** Заглушка вместо пустого экрана во время асинхронного запроса. */
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

/**
 * Единый экран до завершения Telegram-входа.
 *
 * Его рисуют и главная, и root layout: так protected Outlet не
 * монтируется до токена, а публичное поведение главной не расходится.
 */
export function AuthFallback({ state }: { state: Exclude<AuthState, 'ready'> }) {
  const signIn = useAuthState((store) => store.signIn)
  const language = detectLanguage(preferredLanguages())

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
