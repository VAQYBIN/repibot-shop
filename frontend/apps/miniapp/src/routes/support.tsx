import {
  formatDate,
  supportErrorCode,
  type TranslationKey,
  translate,
  useCloseTicket,
  useOpenTicket,
  useReplyToTicket,
  useTicket,
  useTickets,
} from '@repibot/core'
import { Alert, Button, Card, Dialog, EmptyState, Spinner } from '@repibot/ui'
import { createRoute } from '@tanstack/react-router'
import { type FormEvent, useState } from 'react'

import { useLanguage } from '../api'
import { Loading, Retry } from '../auth-fallback'
import { useMainButton } from '../main-button'
import { haptic } from '../telegram'
import { rootRoute } from './root'

const STATUS: Record<string, TranslationKey> = {
  waiting_staff: 'support.status.waiting_staff',
  waiting_user: 'support.status.waiting_user',
  closed: 'support.status.closed',
}

const AUTHOR: Record<string, TranslationKey> = {
  user: 'support.author.user',
  staff: 'support.author.staff',
  system: 'support.author.system',
}

const FIELD =
  'w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-text placeholder:text-text-muted focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none'

function errorText(error: unknown, language: 'ru' | 'en') {
  return error instanceof Error && error.message
    ? error.message
    : translate(language, 'common.error')
}

function label(map: Record<string, TranslationKey>, value: string, language: 'ru' | 'en') {
  const key = map[value]
  return key === undefined ? value : translate(language, key)
}

export function Support() {
  const language = useLanguage()
  const tickets = useTickets()
  const [selected, setSelected] = useState<number | null>(null)
  const thread = useTicket(selected)
  const openTicket = useOpenTicket(language)
  const replyToTicket = useReplyToTicket(language)
  const closeTicket = useCloseTicket(language)
  const [subject, setSubject] = useState('')
  const [answer, setAnswer] = useState('')
  const [closeAsked, setCloseAsked] = useState(false)
  // Признака «поддержка выключена» у API нет: о ней сообщает отказ на попытку
  // написать. Список при этом читается — переписка остаётся с человеком.
  const unavailable =
    supportErrorCode(openTicket.error) === 'support_unavailable' ||
    supportErrorCode(replyToTicket.error) === 'support_unavailable'
  const current = thread.data?.ticket ?? null
  const closed = current?.status === 'closed'

  // Одна и та же главная кнопка ведёт себя как форма под ней: пока переписка
  // не выбрана, отправляет новое обращение, иначе — ответ в открытую.
  const composingNew = selected === null
  const draft = composingNew ? subject : answer
  const sending = composingNew ? openTicket.isPending : replyToTicket.isPending

  async function submitNewTicket() {
    if (subject.trim() === '') return
    let ticket: { id: number }
    try {
      ticket = await openTicket.mutateAsync(
        { body: subject },
        { onSuccess: () => haptic('success'), onError: () => haptic('error') },
      )
    } catch {
      return
    }
    setSubject('')
    // Человек только что написал — открываем ему именно эту переписку.
    setSelected(ticket.id)
  }

  async function submitReply() {
    if (selected === null || answer.trim() === '') return
    try {
      await replyToTicket.mutateAsync(
        { ticketId: selected, body: answer },
        { onSuccess: () => haptic('success'), onError: () => haptic('error') },
      )
    } catch {
      return
    }
    setAnswer('')
  }

  const { supported } = useMainButton({
    text: translate(language, 'support.send'),
    onClick: () => void (composingNew ? submitNewTicket() : submitReply()),
    visible: composingNew ? !unavailable : current !== null && !closed,
    loading: sending,
    disabled: draft.trim() === '',
  })

  async function open(event: FormEvent) {
    event.preventDefault()
    await submitNewTicket()
  }

  async function reply(event: FormEvent) {
    event.preventDefault()
    await submitReply()
  }

  if (tickets.isPending) return <Loading language={language} />
  if (tickets.error !== null)
    return (
      <Retry
        language={language}
        message={errorText(tickets.error, language)}
        onRetry={() => void tickets.refetch()}
      />
    )

  return (
    <main className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-h1 font-semibold text-text">{translate(language, 'support.title')}</h1>
      <p className="text-small text-text-secondary">{translate(language, 'support.hint')}</p>

      {unavailable ? (
        <Card>
          <p role="status" className="text-small text-text">
            {translate(language, 'support.unavailable')}
          </p>
        </Card>
      ) : (
        <Card>
          <form aria-label={translate(language, 'support.new')} onSubmit={open}>
            <h2 className="text-h3 font-semibold text-text">
              {translate(language, 'support.new')}
            </h2>
            <label htmlFor="mini-support-subject" className="sr-only">
              {translate(language, 'support.placeholder')}
            </label>
            <textarea
              id="mini-support-subject"
              rows={3}
              className={`mt-3 ${FIELD}`}
              placeholder={translate(language, 'support.placeholder')}
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
            />
            {supported ? null : (
              // Клиенты без главной кнопки Телеграма обязаны остаться
              // рабочими: без этой ветки написать в поддержку в них нельзя.
              <Button type="submit" className="mt-3" disabled={openTicket.isPending}>
                {translate(language, 'support.send')}
              </Button>
            )}
          </form>
          {openTicket.error !== null ? (
            <Alert tone="error" className="mt-2">
              {errorText(openTicket.error, language)}
            </Alert>
          ) : null}
        </Card>
      )}

      <section aria-labelledby="mini-support-tickets">
        <h2 id="mini-support-tickets" className="text-h3 font-semibold text-text">
          {translate(language, 'support.title')}
        </h2>
        {tickets.data?.length === 0 ? (
          <EmptyState className="mt-3" title={translate(language, 'support.empty')} />
        ) : (
          <ul className="mt-3 space-y-2">
            {tickets.data?.map((ticket) => (
              <li key={ticket.id}>
                <Card>
                  <button
                    type="button"
                    aria-current={ticket.id === selected ? 'true' : undefined}
                    className="flex w-full flex-col gap-1 text-left"
                    onClick={() => setSelected(ticket.id)}
                  >
                    {/* Текст писал человек: показываем как есть, без разметки. */}
                    <span className="font-medium text-text">{ticket.subject}</span>
                    <span className="text-small text-text-secondary">
                      {label(STATUS, ticket.status, language)}
                    </span>
                    <time className="text-small text-text-secondary" dateTime={ticket.created_at}>
                      {formatDate(ticket.created_at, language)}
                    </time>
                  </button>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      {selected === null ? null : (
        <section aria-labelledby="mini-support-thread">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="mini-support-thread" className="text-h3 font-semibold text-text">
              {current?.subject ?? translate(language, 'support.title')}
            </h2>
            {current === null || closed ? null : (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={closeTicket.isPending}
                onClick={() => setCloseAsked(true)}
              >
                {translate(language, 'support.close')}
              </Button>
            )}
          </div>
          {thread.isPending ? (
            <div className="mt-3">
              <Spinner label={translate(language, 'common.loading')} />
            </div>
          ) : thread.error !== null ? (
            <Retry
              language={language}
              message={errorText(thread.error, language)}
              onRetry={() => void thread.refetch()}
            />
          ) : (
            <ul
              aria-label={current?.subject ?? translate(language, 'support.title')}
              className="mt-3 space-y-2"
            >
              {thread.data?.messages.map((message) => (
                <li key={message.id}>
                  <Card>
                    <div className="flex justify-between gap-3">
                      <span className="text-small font-medium text-text">
                        {label(AUTHOR, message.author, language)}
                      </span>
                      <time
                        className="text-small text-text-secondary"
                        dateTime={message.created_at}
                      >
                        {formatDate(message.created_at, language)}
                      </time>
                    </div>
                    {/* Сообщение остаётся текстом: разметку в нём не разбираем. */}
                    <p className="mt-1 whitespace-pre-wrap text-text">{message.body}</p>
                  </Card>
                </li>
              ))}
            </ul>
          )}
          {closed ? (
            <p className="mt-3 text-small text-text-secondary">
              {translate(language, 'support.status.closed')}
            </p>
          ) : (
            <form
              aria-label={translate(language, 'support.reply_placeholder')}
              className="mt-3"
              onSubmit={reply}
            >
              <label htmlFor="mini-support-answer" className="sr-only">
                {translate(language, 'support.reply_placeholder')}
              </label>
              <textarea
                id="mini-support-answer"
                rows={3}
                className={FIELD}
                placeholder={translate(language, 'support.reply_placeholder')}
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
              />
              {supported ? null : (
                // Та же причина: без обычной кнопки ответить в переписку
                // в старом клиенте будет нечем.
                <Button type="submit" className="mt-3" disabled={replyToTicket.isPending}>
                  {translate(language, 'support.send')}
                </Button>
              )}
            </form>
          )}
          {replyToTicket.error !== null && !unavailable ? (
            <Alert tone="error" className="mt-2">
              {errorText(replyToTicket.error, language)}
            </Alert>
          ) : null}
          {closeTicket.error !== null ? (
            <Alert tone="error" className="mt-2">
              {errorText(closeTicket.error, language)}
            </Alert>
          ) : null}
        </section>
      )}

      <Dialog
        open={closeAsked}
        onClose={() => setCloseAsked(false)}
        title={translate(language, 'support.close_confirm')}
        description={translate(language, 'support.close_hint')}
      >
        <Button type="button" variant="secondary" onClick={() => setCloseAsked(false)}>
          {translate(language, 'common.cancel')}
        </Button>
        <Button
          type="button"
          onClick={() => {
            setCloseAsked(false)
            if (selected !== null) {
              closeTicket.mutate(selected, {
                onSuccess: () => haptic('success'),
                onError: () => haptic('error'),
              })
            }
          }}
        >
          {translate(language, 'support.close')}
        </Button>
      </Dialog>
    </main>
  )
}

export const supportRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/support',
  component: Support,
})
