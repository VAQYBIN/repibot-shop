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
import { Alert, Button, Card, cn, Dialog, EmptyState, Spinner, Textarea } from '@repibot/ui'
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
        <h1 className="text-h1 font-semibold text-text">{t('support.title')}</h1>
        <p className="mt-1 text-small text-text-secondary">{t('support.hint')}</p>
      </div>

      {unavailable ? (
        <Card>
          <Alert tone="info">{t('support.unavailable')}</Alert>
        </Card>
      ) : (
        <Card>
          <form aria-label={t('support.new')} onSubmit={open}>
            <h2 className="text-h3 font-medium text-text">{t('support.new')}</h2>
            <label htmlFor="support-subject" className="sr-only">
              {t('support.placeholder')}
            </label>
            <Textarea
              id="support-subject"
              rows={3}
              placeholder={t('support.placeholder')}
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              className="mt-3"
            />
            <Button type="submit" className="mt-3" disabled={openTicket.isPending}>
              {t('support.send')}
            </Button>
          </form>
          {openTicket.error !== null ? (
            <Alert tone="error" className="mt-2">
              {errorText(openTicket.error, language)}
            </Alert>
          ) : null}
        </Card>
      )}

      <section aria-labelledby="support-tickets">
        <h2 id="support-tickets" className="text-h3 font-medium text-text">
          {t('support.title')}
        </h2>
        {tickets.isPending ? (
          <Spinner label={t('common.loading')} className="mt-3" />
        ) : tickets.error !== null ? (
          <Card className="mt-3">
            <Alert tone="error">{errorText(tickets.error, language)}</Alert>
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
                    <span className="text-small text-text-secondary">
                      {label(STATUS, ticket.status, t)}
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
        <section aria-labelledby="support-thread">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="support-thread" className="text-h3 font-medium text-text">
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
            <Spinner label={t('common.loading')} className="mt-3" />
          ) : thread.error !== null ? (
            <Card className="mt-3">
              <Alert tone="error">{errorText(thread.error, language)}</Alert>
              <Button className="mt-3" onClick={() => void thread.refetch()}>
                {t('common.retry')}
              </Button>
            </Card>
          ) : (
            <ul aria-label={current?.subject ?? t('support.title')} className="mt-3 space-y-3">
              {thread.data?.messages.map((message) => {
                const mine = message.author === 'user'
                return (
                  <li key={message.id} className={mine ? 'flex justify-end' : 'flex justify-start'}>
                    {/* Своё прижато вправо и залито акцентной подложкой, чужое
                        лежит слева на поверхности. Подпись остаётся, но теперь
                        она подтверждает то, что и так видно, а не сообщает. */}
                    <div
                      className={cn(
                        'max-w-[85%] rounded-md border px-4 py-3',
                        mine
                          ? 'border-transparent bg-jade-mist'
                          : 'border-border-subtle bg-surface',
                      )}
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-small font-medium text-text">
                          {label(AUTHOR, message.author, t)}
                        </span>
                        <time
                          className="text-caption text-text-secondary"
                          dateTime={message.created_at}
                        >
                          {formatDate(message.created_at, language)}
                        </time>
                      </div>
                      {/* Сообщение остаётся текстом: разметку в нём не разбираем. */}
                      <p className="mt-1 whitespace-pre-wrap text-text">{message.body}</p>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
          {closed ? (
            <Alert tone="info" className="mt-3">
              {t('support.status.closed')}
            </Alert>
          ) : (
            <form aria-label={t('support.reply_placeholder')} className="mt-3" onSubmit={reply}>
              <label htmlFor="support-answer" className="sr-only">
                {t('support.reply_placeholder')}
              </label>
              <Textarea
                id="support-answer"
                rows={3}
                placeholder={t('support.reply_placeholder')}
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
              />
              <Button type="submit" className="mt-3" disabled={replyToTicket.isPending}>
                {t('support.send')}
              </Button>
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
