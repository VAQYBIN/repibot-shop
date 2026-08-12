'use client'

import { translate, useAuthClient } from '@repibot/core'
import { Alert, Spinner } from '@repibot/ui'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'

import { AuthGuard } from '@/components/auth-guard'
import { Lockup } from '@/components/lockup'
import { useProfileLanguage } from '@/lib/i18n'
import { useQueryParam } from '@/lib/query-param'

type Claim = { state: 'claiming' | 'invalid' | 'no_token' } | { state: 'claimed'; days: number }

/**
 * Получение подарочных дней лесенки возврата.
 *
 * Дни начисляются сами при открытии: человек уже нажал на ссылку в письме,
 * просить его нажать ещё одну кнопку не за что.
 */
function Claim() {
  const language = useProfileLanguage()
  const { api } = useAuthClient()
  const queries = useQueryClient()
  const token = useQueryParam('token')
  const [claim, setClaim] = useState<Claim>({ state: 'claiming' })
  // Токен одноразовый: второй запрос вернёт invalid_token, и двойной монтаж в
  // разработке стёр бы уже начисленные дни сообщением о недействительной ссылке.
  const asked = useRef(false)

  useEffect(() => {
    // undefined — адрес ещё не прочитан; сообщить об отсутствии токена сейчас
    // значит соврать тому, у кого он есть.
    if (token === undefined || asked.current) return
    asked.current = true

    if (token === null) {
      setClaim({ state: 'no_token' })
      return
    }

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
    <div className="flex w-full flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">{translate(language, 'winback.title')}</h1>

      {claim.state === 'claiming' ? (
        <Spinner label={translate(language, 'common.loading')} />
      ) : null}

      {claim.state === 'claimed' ? (
        <p role="status" className="text-text-secondary">
          {translate(language, 'winback.claimed').replace('{days}', String(claim.days))}
        </p>
      ) : null}

      {claim.state === 'invalid' || claim.state === 'no_token' ? (
        <Alert tone="error">
          {translate(language, claim.state === 'no_token' ? 'winback.no_token' : 'winback.invalid')}
        </Alert>
      ) : null}

      <a href="/account/subscription" className="text-small text-text-accent hover:underline">
        {translate(language, 'winback.to_subscription')}
      </a>
    </div>
  )
}

/**
 * Страница живёт под гейтом кабинета, хотя открывают её по ссылке из письма:
 * дни начисляются на аккаунт, и он должен быть свой. Токен доказывает право на
 * подарок, но не личность — письмо могло уехать куда угодно вместе с ссылкой.
 * Тем и отличается от отписки, которая намеренно работает без входа.
 */
export default function WinbackPage() {
  const router = useRouter()
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center gap-6 p-6">
      <Lockup size={40} />
      <AuthGuard router={router}>
        <Claim />
      </AuthGuard>
    </main>
  )
}
