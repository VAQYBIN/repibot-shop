'use client'

import { useAuthClient } from '@repibot/core'
import {
  Alert,
  Badge,
  type BadgeTone,
  Button,
  Card,
  cn,
  EmptyState,
  Select,
  Spinner,
} from '@repibot/ui'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { useState } from 'react'

import { AdminPage } from '@/components/admin-page'

type TicketStatus = 'waiting_staff' | 'waiting_user' | 'closed'
type StatusFilter = TicketStatus | 'all'

const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'waiting_staff', label: 'Ждут ответа поддержки' },
  { value: 'waiting_user', label: 'Ждут ответа пользователя' },
  { value: 'closed', label: 'Закрытые' },
]

/**
 * Соответствие тонов повторяет эмодзи в названиях тем супергруппы: красное —
 * то, что ждёт нас, жёлтое — то, что ждёт человека, зелёное — решённое.
 */
const STATUS_TONES: Record<TicketStatus, BadgeTone> = {
  waiting_staff: 'danger',
  waiting_user: 'warning',
  closed: 'success',
}

function statusTone(status: string): BadgeTone {
  return STATUS_TONES[status as TicketStatus] ?? 'neutral'
}

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
    <AdminPage
      title="Обращения"
      description="Ответ отсюда уходит человеку тем же путём, что и ответ из топика поддержки."
    >
      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <section aria-labelledby="tickets-heading" className="flex flex-col gap-3">
          <Card>
            <h2 id="tickets-heading" className="font-medium text-h3 text-text">
              Список
            </h2>
            <label htmlFor="ticket-status" className="mt-4 block font-medium text-small text-text">
              Статус
            </label>
            <Select
              id="ticket-status"
              className="mt-2"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
            >
              {STATUS_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>

            {tickets.isPending ? (
              <div className="mt-4">
                <Spinner label="Загрузка" />
              </div>
            ) : tickets.error !== null ? (
              <Alert tone="error" className="mt-4">
                {errorMessage(tickets.error, 'Не удалось загрузить обращения.')}
              </Alert>
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
                      <span className="block truncate font-medium text-small text-text">
                        {ticket.subject}
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-2 text-caption text-text-muted">
                        <Badge tone={statusTone(ticket.status)}>{statusLabel(ticket.status)}</Badge>
                        {`#${ticket.id} · пользователь ${ticket.user_id}`}
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
            <h2 id="thread-heading" className="font-medium text-h3 text-text">
              Переписка
            </h2>

            {selectedId === null ? (
              <EmptyState className="mt-4" title="Выберите обращение слева" />
            ) : thread.isPending ? (
              <div className="mt-4">
                <Spinner label="Загрузка" />
              </div>
            ) : thread.error !== null ? (
              <Alert tone="error" className="mt-4">
                {errorMessage(thread.error, 'Не удалось загрузить переписку.')}
              </Alert>
            ) : (
              <>
                <p className="mt-1 flex flex-wrap items-center gap-2 text-small text-text-secondary">
                  {thread.data.ticket.subject}
                  <Badge tone={statusTone(thread.data.ticket.status)}>
                    {statusLabel(thread.data.ticket.status)}
                  </Badge>
                  {selected === undefined ? '' : `· пользователь ${selected.user_id}`}
                </p>

                {thread.data.messages.length === 0 ? (
                  <EmptyState className="mt-4" title="Сообщений пока нет" />
                ) : (
                  <ol className="mt-4 flex flex-col gap-3">
                    {thread.data.messages.map((message) => {
                      // Прижимаем к разным краям: ответ персонала — вправо, на
                      // подложке бренда; сообщение человека — влево, нейтральным.
                      const staff = message.author === 'staff'
                      return (
                        <li
                          key={message.id}
                          className={staff ? 'flex justify-end' : 'flex justify-start'}
                        >
                          <div
                            className={cn(
                              'max-w-[85%] rounded-md border px-4 py-3',
                              staff
                                ? 'border-transparent bg-jade-mist'
                                : 'border-border-subtle bg-surface',
                            )}
                          >
                            <p className="text-caption text-text-muted">
                              {`${authorLabel(message.author)} · ${formatMoment(message.created_at)}`}
                            </p>
                            {/* Текст писал человек: выводим как есть, переносы
                                сохраняем, разметку не разбираем. */}
                            <p className="mt-1 whitespace-pre-wrap break-words text-small text-text">
                              {message.body}
                            </p>
                          </div>
                        </li>
                      )
                    })}
                  </ol>
                )}

                {closed ? (
                  <p className="mt-4 text-small text-text-secondary">
                    Обращение закрыто. Ответить нельзя — человек откроет новое.
                  </p>
                ) : (
                  <form onSubmit={submitReply} className="mt-4 flex flex-col gap-3">
                    <label htmlFor="reply-body" className="font-medium text-small text-text">
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
                      <Alert tone="error">
                        {errorMessage(sendReply.error, 'Не удалось отправить ответ.')}
                      </Alert>
                    )}
                    {closeTicket.error === null ? null : (
                      <Alert tone="error">
                        {errorMessage(closeTicket.error, 'Не удалось закрыть обращение.')}
                      </Alert>
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
    </AdminPage>
  )
}
