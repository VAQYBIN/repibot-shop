'use client'

import { Card } from '@repibot/ui'
import { useEffect, useRef, useState } from 'react'

import { Lockup } from '@/components/lockup'
import { useBrowserLanguage } from '@/lib/i18n'
import { useQueryParam } from '@/lib/query-param'

/**
 * Отписка от маркетинговых сообщений по ссылке из письма.
 *
 * Страница публичная и намеренно живёт вне группы (auth): письмо открывают в
 * том браузере, где заведена почта, а не в том, где открыт кабинет. Под гейтом
 * такого человека увело бы на /login, он не вспомнил бы пароль и отписался бы
 * кнопкой «спам» — а это бьёт по доставляемости всей нашей почты, включая чеки.
 * Операцию авторизует сам токен, эндпоинт тоже без авторизации.
 *
 * Запрос идёт обычным fetch, а не типизированным клиентом: клиент подставляет
 * заголовок Authorization, а здесь его неоткуда взять и он не нужен.
 *
 * Подписи лежат прямо здесь, а не в общем словаре: страница одноразовая, её
 * видят один раз в жизни, и три строки в общем словаре пережили бы её саму.
 */

const TEXTS = {
  ru: {
    title: 'Отписка от рассылки',
    working: 'Отписываем…',
    done: 'Готово. Предложения больше не придут.',
    kept: 'Сообщения об оплате, окончании подписки и ответах поддержки остаются: без них можно молча потерять доступ.',
    failed: 'Ссылка недействительна. Отписаться можно в кабинете, в разделе уведомлений.',
    account: 'Открыть кабинет',
  },
  en: {
    title: 'Unsubscribe',
    working: 'Unsubscribing…',
    done: 'Done. You will not get offers any more.',
    kept: 'Notices about payments, subscription expiry and support replies stay: without them you could lose access without knowing.',
    failed: 'This link is not valid. You can unsubscribe in your account, under notifications.',
    account: 'Open your account',
  },
} as const

export default function UnsubscribePage() {
  const language = useBrowserLanguage()
  const texts = TEXTS[language] ?? TEXTS.ru
  const token = useQueryParam('token')
  const [state, setState] = useState<'working' | 'done' | 'failed'>('working')
  // Двойной эффект в разработке отправил бы второй запрос по той же ссылке.
  const asked = useRef(false)

  useEffect(() => {
    if (token === undefined || asked.current) return
    asked.current = true

    if (token === null) {
      setState('failed')
      return
    }

    void fetch('/api/unsubscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
      .then((response) => setState(response.ok ? 'done' : 'failed'))
      .catch(() => setState('failed'))
  }, [token])

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center gap-6 p-6">
      <Lockup size={40} />
      <Card>
        <div className="flex w-full flex-col gap-4">
          <h1 className="text-2xl font-semibold text-text">{texts.title}</h1>

          {state === 'working' ? <p className="text-text-secondary">{texts.working}</p> : null}

          {state === 'done' ? (
            <>
              <p className="text-text-secondary">{texts.done}</p>
              <p className="text-sm text-text-secondary">{texts.kept}</p>
            </>
          ) : null}

          {state === 'failed' ? (
            <p role="alert" className="text-sm text-danger">
              {texts.failed}
            </p>
          ) : null}

          <a href="/account" className="text-sm text-text-accent hover:underline">
            {texts.account}
          </a>
        </div>
      </Card>
    </main>
  )
}
