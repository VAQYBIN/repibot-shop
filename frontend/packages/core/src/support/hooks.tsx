'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { components } from '../api/schema'
import { messageFrom } from '../auth/errors'
import { useAuthClient } from '../auth/hooks'
import { type Language, type TranslationKey, translate } from '../i18n/index'

export type TicketResponse = components['schemas']['TicketResponse']
export type TicketMessageResponse = components['schemas']['TicketMessageResponse']
export type TicketThreadResponse = components['schemas']['TicketThreadResponse']
export type OpenTicketRequest = components['schemas']['OpenTicketRequest']

/** Номер обращения приходит с телом ответа: одна форма отвечает в любое из них. */
export interface TicketReplyInput {
  ticketId: number
  body: string
}

const TICKETS_QUERY_KEY = ['tickets'] as const

function ticketQueryKey(ticketId: number | null) {
  return ['ticket', ticketId] as const
}

/** Как часто спрашиваем об ответе поддержки, пока ход за ней. */
const TICKET_POLL_MS = 15_000

/**
 * Отказы поддержки со своими словами.
 *
 * Общий словарь `errorMessageKey` про них не знает, а `rate_limited` там
 * объясняет паузу входа: у поддержки она короче и фраза другая.
 */
const SUPPORT_ERRORS: Record<string, TranslationKey> = {
  support_unavailable: 'support.unavailable',
  too_many_tickets: 'support.error.too_many_tickets',
  ticket_closed: 'support.error.ticket_closed',
  rate_limited: 'support.error.rate_limited',
}

/** Отказ с сохранённым кодом: по тексту экран решать не может, тексты переводятся. */
class SupportError extends Error {
  readonly code: string | undefined

  constructor(message: string, code: string | undefined) {
    super(message)
    this.name = 'SupportError'
    this.code = code
  }
}

/** Код отказа, если ошибка пришла от поддержки. Экран прячет форму по нему. */
export function supportErrorCode(error: unknown): string | undefined {
  return error instanceof SupportError ? error.code : undefined
}

function refusal(error: unknown, language: Language): SupportError {
  const code = (error as { error?: { code?: string } } | undefined)?.error?.code
  const key = code === undefined ? undefined : SUPPORT_ERRORS[code]
  const message = key === undefined ? messageFrom(error, language) : translate(language, key)
  return new SupportError(message, code)
}

/**
 * Список обращений. Читается и при выключенной поддержке: переписка остаётся
 * доказательством того, что было обещано, даже когда написать уже некуда.
 */
export function useTickets() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: TICKETS_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/support/tickets')
      if (error || !data) throw error ?? new Error('пустой ответ /api/support/tickets')
      return data
    },
  })
}

/**
 * Переписка выбранного обращения.
 *
 * Пока ход за поддержкой, экран спрашивает сам: ответ приходит на сервер, а не
 * в открытую страницу, и человек не должен перезагружать её, чтобы увидеть
 * ответ. Как только ход перешёл к человеку или обращение закрыто, вопросы
 * прекращаются — новостей с той стороны больше не будет.
 */
export function useTicket(ticketId: number | null) {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ticketQueryKey(ticketId),
    // Без выбранного обращения читать нечего, и номера у запроса тоже нет.
    enabled: ticketId !== null,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/support/tickets/{ticket_id}', {
        params: { path: { ticket_id: ticketId as number } },
      })
      if (error || !data) throw error ?? new Error('пустой ответ /api/support/tickets/{id}')
      return data
    },
    // Разговор идёт минутами: вернувшийся человек обязан увидеть ответ сразу,
    // а не тот снимок переписки, который остался с прошлого захода.
    refetchOnWindowFocus: 'always',
    refetchInterval: (polled) =>
      polled.state.data?.ticket.status === 'waiting_staff' ? TICKET_POLL_MS : false,
  })
}

/** Новое обращение меняет состав списка, поэтому список после него устарел. */
export function useOpenTicket(language: Language = 'ru') {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: OpenTicketRequest) => {
      const { data, error } = await api.POST('/api/support/tickets', { body: input })
      if (error || !data) throw refusal(error, language)
      return data
    },
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: TICKETS_QUERY_KEY })
    },
  })
}

/**
 * Ответ человека переводит обращение в ожидание поддержки, поэтому устаревают
 * оба снимка: и переписка, и список, где у обращения написан статус.
 */
export function useReplyToTicket(language: Language = 'ru') {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async ({ ticketId, body }: TicketReplyInput) => {
      const { data, error } = await api.POST('/api/support/tickets/{ticket_id}/messages', {
        params: { path: { ticket_id: ticketId } },
        body: { body },
      })
      if (error || !data) throw refusal(error, language)
      return data
    },
    onSuccess: async (_message, { ticketId }) => {
      await Promise.all([
        queries.invalidateQueries({ queryKey: ticketQueryKey(ticketId) }),
        queries.invalidateQueries({ queryKey: TICKETS_QUERY_KEY }),
      ])
    },
  })
}

/** Закрытие меняет статус там же, где и ответ: в переписке и в списке. */
export function useCloseTicket(language: Language = 'ru') {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (ticketId: number) => {
      const { data, error } = await api.POST('/api/support/tickets/{ticket_id}/close', {
        params: { path: { ticket_id: ticketId } },
      })
      if (error || !data) throw refusal(error, language)
      return data
    },
    onSuccess: async (_ticket, ticketId) => {
      await Promise.all([
        queries.invalidateQueries({ queryKey: ticketQueryKey(ticketId) }),
        queries.invalidateQueries({ queryKey: TICKETS_QUERY_KEY }),
      ])
    },
  })
}
