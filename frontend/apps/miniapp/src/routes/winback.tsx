import { translate, useAuthClient } from '@repibot/core'
import { Alert, Card } from '@repibot/ui'
import { useQueryClient } from '@tanstack/react-query'
import { createRoute, Link } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'

import { useLanguage } from '../api'
import { rootRoute } from './root'

type Claim = { state: 'claiming' | 'invalid' | 'no_token' } | { state: 'claimed'; days: number }

/**
 * Экран получения подарочных дней лесенки возврата.
 *
 * Сюда приходят по ссылке из письма, а не из меню, поэтому в навигации экрана
 * нет. Дни начисляются сами при открытии: человек уже нажал на ссылку, просить
 * его нажать ещё одну кнопку не за что.
 *
 * Токен приходит пропом, а не читается из адреса здесь: так экран проверяется
 * без роутера — в том числе на двойной монтаж, который роутер прячет за своим
 * Suspense.
 */
export function Winback({ token }: { token: string | null }) {
  const language = useLanguage()
  const { api } = useAuthClient()
  const queries = useQueryClient()
  const [claim, setClaim] = useState<Claim>({ state: token === null ? 'no_token' : 'claiming' })
  // Токен одноразовый: второй запрос вернёт invalid_token, и двойной монтаж в
  // разработке стёр бы уже начисленные дни сообщением о недействительной ссылке.
  const asked = useRef(false)

  useEffect(() => {
    if (token === null || asked.current) return
    asked.current = true

    void api.POST('/api/winback/claim', { body: { token } }).then(({ data, error }) => {
      if (error !== undefined || data === undefined) {
        setClaim({ state: 'invalid' })
        return
      }
      setClaim({ state: 'claimed', days: data.days })
      // Срок подписки только что сдвинулся: старый снимок в кэше показал бы
      // прежнюю дату тому, кто сразу перейдёт по ссылке ниже.
      void queries.invalidateQueries({ queryKey: ['subscription'] })
    })
  }, [api, queries, token])

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">{translate(language, 'winback.title')}</h1>
      <Card>
        {claim.state === 'claiming' ? (
          <p role="status" className="text-text-secondary">
            {translate(language, 'winback.claiming')}
          </p>
        ) : null}

        {claim.state === 'claimed' ? (
          <p role="status" className="text-text">
            {translate(language, 'winback.claimed').replace('{days}', String(claim.days))}
          </p>
        ) : null}

        {claim.state === 'invalid' || claim.state === 'no_token' ? (
          <Alert tone="error">
            {translate(
              language,
              claim.state === 'no_token' ? 'winback.no_token' : 'winback.invalid',
            )}
          </Alert>
        ) : null}

        <Link to="/subscription" className="mt-4 inline-block text-small text-text-accent">
          {translate(language, 'winback.to_subscription')}
        </Link>
      </Card>
    </main>
  )
}

function WinbackScreen() {
  const { token } = winbackRoute.useSearch()
  return <Winback token={token} />
}

export const winbackRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/winback',
  // Ссылку из письма могли обрезать или переписать: отсутствие токена — обычное
  // значение, а не повод уронить экран разбором строки запроса.
  validateSearch: (search: Record<string, unknown>): { token: string | null } => ({
    token: typeof search.token === 'string' && search.token !== '' ? search.token : null,
  }),
  component: WinbackScreen,
})
