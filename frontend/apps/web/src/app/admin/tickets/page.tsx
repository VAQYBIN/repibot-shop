'use client'

import { useAuthClient } from '@repibot/core'
import { Button, Card, EmptyState } from '@repibot/ui'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { useState } from 'react'

type TicketStatus = 'waiting_staff' | 'waiting_user' | 'closed'
type StatusFilter = TicketStatus | 'all'

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'waiting_staff', label: 'Ждут ответа поддержки' },
  { value: 'waiting_user', label: 'Ждут ответа пользователя' },
  { value: 'closed', label: 'Закрытые' },
]

/**
 * Переписку перечитываем сама собой, пока обращение живое: человек дописывает
 * в свой топик, пока сотрудник печатает ответ, и без опроса сотрудник ответил
 * бы на устаревшую картину.
 */
const THREAD_POLL_MS = 15_000

function statusLabel(status: string): string {
  if (status === 'waiting_staff') return 'Ждёт ответа поддержки'
  if (status === 'waiting_user') return 'Ждёт ответа пользователя'
  if (status === 'closed') return 'Закрыто'
  return status
}

function authorLabel(author: string): string {
  if (author === 'user') return 'Пользователь'
  if (author === 'staff') return 'Поддержка'
  if (author === 'system') return 'Система'
  return author
}

function formatMoment(value: string): string {
  return new Date(value).toLocaleString('ru-RU')
}

/**
 * Ответ сервера приходит телом `{"error": {"code", "message"}}`. Из кодов нам
 * важен только `ticket_closed`: он значит, что обращение закрыли, пока ответ
 * писали, и повторять отправку бессмысленно.
 */
function errorMessage(error: unknown, fallback: string): string {
  const code = (error as { error?: { code?: string } } | null | undefined)?.error?.code
  if (code === 'ticket_closed') return 'Обращение уже закрыто — ответ не отправлен.'
  return fallback
}

export default function AdminTicketsPage() {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [reply, setReply] = useState('')

  const tickets = useQuery({
    queryKey: ['admin', 'tickets', statusFilter],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/tickets', {
        params: { query: statusFilter === 'all' ? {} : { status: statusFilter } },
      })
      if (error || !data) throw error ?? new Error('пустой список обращений')
      return data
    },
  })

  const thread = useQuery({
    queryKey: ['admin', 'ticket', selectedId],
    enabled: selectedId !== null,
    // Закрытое обращение больше не меняется, стучаться в сервер незачем.
    refetchInterval: (query) =>
      query.state.data?.ticket.status === 'closed' ? false : THREAD_POLL_MS,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/tickets/{ticket_id}', {
        params: { path: { ticket_id: selectedId as number } },
      })
      if (error || !data) throw error ?? new Error('пустая переписка обращения')
      return data
    },
  })

  // Адресата называет сама переписка, а список — только запасной источник:
  // при отборе, из которого выбранное обращение выпало, строки в списке уже
  // нет, и подпись разговора иначе пропала бы.
  const selected = thread.data?.ticket ?? tickets.data?.find((ticket) => ticket.id === selectedId)
  const threadStatus = thread.data?.ticket.status
  const closed = threadStatus === 'closed'

  async function invalidate(): Promise<void> {
    // Список тоже устаревает: ответ сотрудника переводит обращение в другой
    // статус, и строка списка должна это показать.
    await Promise.all([
      queries.invalidateQueries({ queryKey: ['admin', 'ticket', selectedId] }),
      queries.invalidateQueries({ queryKey: ['admin', 'tickets'] }),
    ])
  }

  const sendReply = useMutation({
    mutationFn: async (body: string) => {
      const { error } = await api.POST('/api/admin/tickets/{ticket_id}/messages', {
        params: { path: { ticket_id: selectedId as number } },
        body: { body },
      })
      if (error) throw error
    },
    onSuccess: async () => {
      setReply('')
      await invalidate()
    },
  })

  const closeTicket = useMutation({
    mutationFn: async () => {
      // Ответ 204: тела нет, разбирать нечего — только признак отказа.
      const { error } = await api.POST('/api/admin/tickets/{ticket_id}/close', {
        params: { path: { ticket_id: selectedId as number } },
      })
      if (error) throw error
    },
    onSuccess: invalidate,
  })

  function submitReply(event: FormEvent) {
    event.preventDefault()
    const body = reply.trim()
    if (body === '' || selectedId === null) return
    sendReply.mutate(body)
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6 text-text">
      <header>
        <h1 className="text-2xl font-semibold">Обращения</h1>
        <p className="mt-1 max-w-prose text-sm text-text-secondary">
          Ответ отсюда уходит человеку тем же путём, что и ответ из топика поддержки.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <section aria-labelledby="tickets-heading" className="flex flex-col gap-3">
          <Card>
            <h2 id="tickets-heading" className="text-lg font-semibold text-text">
              Список
            </h2>
            <label htmlFor="ticket-status" className="mt-4 block text-sm font-medium text-text">
              Статус
            </label>
            <select
              id="ticket-status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
              className="mt-2 h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-text focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none"
            >
              {STATUS_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>

            {tickets.isPending ? (
              <p className="mt-4 text-sm text-text-secondary">Загрузка…</p>
            ) : tickets.error !== null ? (
              <p role="alert" className="mt-4 text-sm text-danger">
                {errorMessage(tickets.error, 'Не удалось загрузить обращения.')}
              </p>
            ) : tickets.data.length === 0 ? (
              <EmptyState className="mt-4" title="Обращений с таким статусом нет" />
            ) : (
              <ul aria-label="Обращения" className="mt-4 flex flex-col gap-2">
                {tickets.data.map((ticket) => (
                  <li key={ticket.id}>
                    <button
                      type="button"
                      aria-pressed={ticket.id === selectedId}
                      onClick={() => {
                        setSelectedId(ticket.id)
                        // Черновик писали другому человеку — переносить его в
                        // чужую переписку опаснее, чем потерять.
                        setReply('')
                      }}
                      className="w-full rounded-md border border-border-subtle px-3 py-2 text-left aria-pressed:border-accent aria-pressed:bg-surface-sunken"
                    >
                      <span className="block truncate text-sm font-medium text-text">
                        {ticket.subject}
                      </span>
                      <span className="mt-1 block text-xs text-text-muted">
                        {`#${ticket.id} · ${statusLabel(ticket.status)} · пользователь ${ticket.user_id}`}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>

        <section aria-labelledby="thread-heading">
          <Card>
            <h2 id="thread-heading" className="text-lg font-semibold text-text">
              Переписка
            </h2>

            {selectedId === null ? (
              <EmptyState className="mt-4" title="Выберите обращение слева" />
            ) : thread.isPending ? (
              <p className="mt-4 text-sm text-text-secondary">Загрузка…</p>
            ) : thread.error !== null ? (
              <p role="alert" className="mt-4 text-sm text-danger">
                {errorMessage(thread.error, 'Не удалось загрузить переписку.')}
              </p>
            ) : (
              <>
                <p className="mt-1 text-sm text-text-secondary">
                  {`${thread.data.ticket.subject} · ${statusLabel(thread.data.ticket.status)}`}
                  {selected === undefined ? '' : ` · пользователь ${selected.user_id}`}
                </p>

                {thread.data.messages.length === 0 ? (
                  <EmptyState className="mt-4" title="Сообщений пока нет" />
                ) : (
                  <ol className="mt-4 flex flex-col gap-3">
                    {thread.data.messages.map((message) => (
                      <li key={message.id} className="rounded-md bg-surface-sunken p-3">
                        <p className="text-xs text-text-muted">
                          {`${authorLabel(message.author)} · ${formatMoment(message.created_at)}`}
                        </p>
                        {/* Текст писал человек: выводим как есть, переносы
                            сохраняем, разметку не разбираем. */}
                        <p className="mt-1 text-sm whitespace-pre-wrap break-words text-text">
                          {message.body}
                        </p>
                      </li>
                    ))}
                  </ol>
                )}

                {closed ? (
                  <p className="mt-4 text-sm text-text-secondary">
                    Обращение закрыто. Ответить нельзя — человек откроет новое.
                  </p>
                ) : (
                  <form onSubmit={submitReply} className="mt-4 flex flex-col gap-3">
                    <label htmlFor="reply-body" className="text-sm font-medium text-text">
                      Ответ поддержки
                    </label>
                    <textarea
                      id="reply-body"
                      rows={4}
                      value={reply}
                      onChange={(event) => setReply(event.target.value)}
                      className="w-full rounded-md border border-border-subtle bg-surface px-3 py-2 text-text focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none"
                    />

                    {sendReply.error === null ? null : (
                      <p role="alert" className="text-sm text-danger">
                        {errorMessage(sendReply.error, 'Не удалось отправить ответ.')}
                      </p>
                    )}
                    {closeTicket.error === null ? null : (
                      <p role="alert" className="text-sm text-danger">
                        {errorMessage(closeTicket.error, 'Не удалось закрыть обращение.')}
                      </p>
                    )}

                    <div className="flex flex-wrap items-center gap-3">
                      <Button type="submit" disabled={reply.trim() === '' || sendReply.isPending}>
                        Отправить ответ
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={closeTicket.isPending}
                        onClick={() => closeTicket.mutate()}
                      >
                        Закрыть обращение
                      </Button>
                    </div>
                  </form>
                )}
              </>
            )}
          </Card>
        </section>
      </div>
    </main>
  )
}
