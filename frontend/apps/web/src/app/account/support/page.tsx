'use client'

import {
  formatDate,
  supportErrorCode,
  type TranslationKey,
  useCloseTicket,
  useOpenTicket,
  useReplyToTicket,
  useTicket,
  useTickets,
} from '@repibot/core'
import { Button, Card, Dialog, EmptyState } from '@repibot/ui'
import { type FormEvent, useState } from 'react'

import { errorText, type Translate, useProfileLanguage, useTranslate } from '@/lib/i18n'

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

function label(map: Record<string, TranslationKey>, value: string, t: Translate) {
  const key = map[value]
  return key === undefined ? value : t(key)
}

export default function SupportPage() {
  const language = useProfileLanguage()
  const t = useTranslate(language)
  const tickets = useTickets()
  const [selected, setSelected] = useState<number | null>(null)
  const thread = useTicket(selected)
  const openTicket = useOpenTicket(language)
  const replyToTicket = useReplyToTicket(language)
  const closeTicket = useCloseTicket(language)
  const [subject, setSubject] = useState('')
  const [answer, setAnswer] = useState('')
  const [closeAsked, setCloseAsked] = useState(false)
  // Другого признака у API нет: выключенную поддержку показывает отказ на
  // попытку написать. Список при этом читается — переписка остаётся с человеком.
  const unavailable =
    supportErrorCode(openTicket.error) === 'support_unavailable' ||
    supportErrorCode(replyToTicket.error) === 'support_unavailable'
  const current = thread.data?.ticket ?? null
  const closed = current?.status === 'closed'

  async function open(event: FormEvent) {
    event.preventDefault()
    if (subject.trim() === '') return
    let ticket: { id: number }
    try {
      ticket = await openTicket.mutateAsync({ body: subject })
    } catch {
      return
    }
    setSubject('')
    // Человек только что написал — показываем ему именно эту переписку.
    setSelected(ticket.id)
  }

  async function reply(event: FormEvent) {
    event.preventDefault()
    if (selected === null || answer.trim() === '') return
    try {
      await replyToTicket.mutateAsync({ ticketId: selected, body: answer })
    } catch {
      return
    }
    setAnswer('')
  }

  return (
    <main className="flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-text">{t('support.title')}</h1>
        <p className="mt-1 text-sm text-text-secondary">{t('support.hint')}</p>
      </div>

      {unavailable ? (
        <Card>
          <p role="status" className="text-sm text-text">
            {t('support.unavailable')}
          </p>
        </Card>
      ) : (
        <Card>
          <form aria-label={t('support.new')} onSubmit={open}>
            <h2 className="text-lg font-semibold text-text">{t('support.new')}</h2>
            <label htmlFor="support-subject" className="sr-only">
              {t('support.placeholder')}
            </label>
            <textarea
              id="support-subject"
              rows={3}
              placeholder={t('support.placeholder')}
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              className="mt-3 w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-text placeholder:text-text-muted focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none"
            />
            <Button type="submit" className="mt-3" disabled={openTicket.isPending}>
              {t('support.send')}
            </Button>
          </form>
          {openTicket.error !== null ? (
            <p role="alert" className="mt-2 text-sm text-danger">
              {errorText(openTicket.error, language)}
            </p>
          ) : null}
        </Card>
      )}

      <section aria-labelledby="support-tickets">
        <h2 id="support-tickets" className="text-lg font-semibold text-text">
          {t('support.title')}
        </h2>
        {tickets.isPending ? (
          <p role="status" className="mt-3 text-text-secondary">
            {t('common.loading')}
          </p>
        ) : tickets.error !== null ? (
          <Card className="mt-3">
            <p role="alert" className="text-danger">
              {errorText(tickets.error, language)}
            </p>
            <Button className="mt-3" onClick={() => void tickets.refetch()}>
              {t('common.retry')}
            </Button>
          </Card>
        ) : tickets.data?.length === 0 ? (
          <EmptyState className="mt-3" title={t('support.empty')} />
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
                    <span className="text-sm text-text-secondary">
                      {label(STATUS, ticket.status, t)}
                    </span>
                    <time className="text-sm text-text-secondary" dateTime={ticket.created_at}>
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
        <section aria-labelledby="support-thread">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="support-thread" className="text-lg font-semibold text-text">
              {current?.subject ?? t('support.title')}
            </h2>
            {current === null || closed ? null : (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={closeTicket.isPending}
                onClick={() => setCloseAsked(true)}
              >
                {t('support.close')}
              </Button>
            )}
          </div>
          {thread.isPending ? (
            <p role="status" className="mt-3 text-text-secondary">
              {t('common.loading')}
            </p>
          ) : thread.error !== null ? (
            <Card className="mt-3">
              <p role="alert" className="text-danger">
                {errorText(thread.error, language)}
              </p>
              <Button className="mt-3" onClick={() => void thread.refetch()}>
                {t('common.retry')}
              </Button>
            </Card>
          ) : (
            <ul aria-label={current?.subject ?? t('support.title')} className="mt-3 space-y-2">
              {thread.data?.messages.map((message) => (
                <li key={message.id}>
                  <Card>
                    <div className="flex justify-between gap-3">
                      <span className="text-sm font-medium text-text">
                        {label(AUTHOR, message.author, t)}
                      </span>
                      <time className="text-sm text-text-secondary" dateTime={message.created_at}>
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
            <p className="mt-3 text-sm text-text-secondary">{t('support.status.closed')}</p>
          ) : (
            <form aria-label={t('support.reply_placeholder')} className="mt-3" onSubmit={reply}>
              <label htmlFor="support-answer" className="sr-only">
                {t('support.reply_placeholder')}
              </label>
              <textarea
                id="support-answer"
                rows={3}
                placeholder={t('support.reply_placeholder')}
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                className="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-text placeholder:text-text-muted focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none"
              />
              <Button type="submit" className="mt-3" disabled={replyToTicket.isPending}>
                {t('support.send')}
              </Button>
            </form>
          )}
          {replyToTicket.error !== null && !unavailable ? (
            <p role="alert" className="mt-2 text-sm text-danger">
              {errorText(replyToTicket.error, language)}
            </p>
          ) : null}
          {closeTicket.error !== null ? (
            <p role="alert" className="mt-2 text-sm text-danger">
              {errorText(closeTicket.error, language)}
            </p>
          ) : null}
        </section>
      )}

      <Dialog
        open={closeAsked}
        onClose={() => setCloseAsked(false)}
        title={t('support.close_confirm')}
        description={t('support.close_hint')}
      >
        <Button type="button" variant="ghost" onClick={() => setCloseAsked(false)}>
          {t('common.cancel')}
        </Button>
        <Button
          type="button"
          onClick={() => {
            setCloseAsked(false)
            if (selected !== null) closeTicket.mutate(selected)
          }}
        >
          {t('support.close')}
        </Button>
      </Dialog>
    </main>
  )
}
