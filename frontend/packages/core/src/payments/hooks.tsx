import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import type { components } from '../api/schema'
import { messageFrom } from '../auth/errors'
import { useAuthClient } from '../auth/hooks'
import type { Language } from '../i18n/index'

export type CreateOrderRequest = components['schemas']['CreateOrderRequest']
export type OrderResponse = components['schemas']['OrderResponse']
export type RedeemGiftRequest = components['schemas']['RedeemGiftRequest']
export type SubscriptionStateResponse = components['schemas']['SubscriptionStateResponse']
export type AutoRenewRequest = components['schemas']['AutoRenewRequest']
export type AutoRenewResponse = components['schemas']['AutoRenewResponse']
export type GiftVoucherResponse = components['schemas']['GiftVoucherResponse']
export type PaymentMethodResponse = components['schemas']['PaymentMethodResponse']
export type CardBindingRequest = components['schemas']['CardBindingRequest']
export type CardBindingResponse = components['schemas']['CardBindingResponse']

const ORDERS_QUERY_KEY = ['orders'] as const
const SUBSCRIPTION_QUERY_KEY = ['subscription'] as const
const GIFTS_QUERY_KEY = ['gifts'] as const
const PAYMENT_METHOD_QUERY_KEY = ['payment-method'] as const

export function useOrders() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ORDERS_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/orders')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/orders')
      return data
    },
    // Оплата заканчивается у провайдера, пока приложение свёрнуто, поэтому
    // возврат перечитывает заказы независимо от срока годности снимка:
    // обычное правило пропустило бы оплату, уложившуюся в эти секунды.
    refetchOnWindowFocus: 'always',
  })
}

/** История ваучеров принадлежит серверу; клиент не синтезирует её из заказов. */
export function useGifts() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: GIFTS_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/gifts')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/gifts')
      return data
    },
  })
}

/** Как часто спрашиваем о начатой привязке. Дольше — и возврат ощущается зависшим. */
const BINDING_POLL_MS = 4000

/**
 * Сохранённая карта живёт отдельно от подписки: её название и доступность
 * привязки без оплаты знает только сервер, клиент их не выводит.
 *
 * Пока по начатой привязке нет ответа, экран спрашивает сам. Ответ провайдера
 * приходит не в тот момент, когда человек вернулся в приложение: один запрос
 * на возврате попадает в промежуток между возвращением и ответом и показывает
 * «карта не привязана» тому, кто карту только что привязал. Ждать нечего, как
 * только сервер снимает `binding_pending`, — вопросы прекращаются сами.
 */
export function usePaymentMethod() {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  const query = useQuery({
    queryKey: PAYMENT_METHOD_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/payment-method')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/payment-method')
      return data
    },
    // Тот же запрос дочитывает привязку у провайдера, так что возврат из
    // браузера обязан его повторить, а не показывать снимок «карты нет».
    refetchOnWindowFocus: 'always',
    refetchInterval: (polled) =>
      polled.state.data?.binding_pending === true ? BINDING_POLL_MS : false,
    // Форму провайдера человек проходит вне приложения, и на телефоне оно всё
    // это время свёрнуто: опрос, привязанный к активному окну, не возобновился
    // бы, не приди о возвращении отдельное событие.
    refetchIntervalInBackground: true,
  })
  const awaiting = query.data?.binding_pending === true
  const wasAwaiting = useRef(false)
  useEffect(() => {
    // Привязка включает автоплатёж на сервере, поэтому снимок подписки,
    // снятый до неё, устарел вместе с окончанием ожидания.
    if (wasAwaiting.current && !awaiting)
      void queries.invalidateQueries({ queryKey: SUBSCRIPTION_QUERY_KEY })
    wasAwaiting.current = awaiting
  }, [awaiting, queries])
  return query
}

/**
 * Вместе с картой сервер выключает автоплатёж: списывать становится нечем.
 * Поэтому снимок подписки после отвязки тоже устарел и перечитывается.
 */
export function useUnlinkCard(language: Language = 'ru') {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE('/api/me/payment-method')
      if (error) throw new Error(messageFrom(error, language))
    },
    onSuccess: async () => {
      await Promise.all([
        queries.invalidateQueries({ queryKey: PAYMENT_METHOD_QUERY_KEY }),
        queries.invalidateQueries({ queryKey: SUBSCRIPTION_QUERY_KEY }),
      ])
    },
  })
}

/**
 * Привязка без списания заканчивается на форме провайдера, поэтому здесь
 * кэш не трогаем: карта появится только после подтверждения на стороне
 * провайдера, а о нём нам сообщит следующий запрос состояния.
 *
 * Поверхность возврата приходит параметром мутации — как и тело заказа в
 * `useCreateOrder`: обе точки входа в оплату называют её на месте вызова, и
 * тело запроса остаётся ровно тем, что описано в схеме. Сам адрес возврата
 * собирает сервер: принимать URL от клиента значило бы открытый редирект.
 */
export function useStartCardBinding(language: Language = 'ru') {
  const { api } = useAuthClient()
  return useMutation({
    mutationFn: async (input: CardBindingRequest) => {
      const { data, error } = await api.POST('/api/me/payment-method/bindings', { body: input })
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
  })
}

export function useCreateOrder(language: Language = 'ru') {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: CreateOrderRequest) => {
      const { data, error } = await api.POST('/api/me/orders', { body: input })
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: async (order) => {
      queries.setQueryData<OrderResponse[]>(ORDERS_QUERY_KEY, (previous) => [
        order,
        ...(previous ?? []).filter(({ id }) => id !== order.id),
      ])
      await Promise.all([
        queries.invalidateQueries({ queryKey: ORDERS_QUERY_KEY }),
        queries.invalidateQueries({ queryKey: SUBSCRIPTION_QUERY_KEY }),
      ])
    },
  })
}

export function useRedeemGift(language: Language = 'ru') {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: RedeemGiftRequest) => {
      const { data, error } = await api.POST('/api/me/gifts/redeem', { body: input })
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: async (subscription) => {
      queries.setQueryData(SUBSCRIPTION_QUERY_KEY, subscription)
      await queries.invalidateQueries({ queryKey: GIFTS_QUERY_KEY })
    },
  })
}

/**
 * Переключатель меняет только локальный снимок подписки до ответа, чтобы UI не
 * мигал. Ответ API всё равно заменяет оптимистичное значение — сервер решает,
 * доступна ли настройка для текущей подписки.
 */
export function useAutoRenew(language: Language = 'ru') {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (input: AutoRenewRequest) => {
      const { data, error } = await api.PUT('/api/me/subscription/auto-renew', { body: input })
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
    onMutate: async (input) => {
      await queries.cancelQueries({ queryKey: SUBSCRIPTION_QUERY_KEY })
      const previous = queries.getQueryData<SubscriptionStateResponse>(SUBSCRIPTION_QUERY_KEY)
      queries.setQueryData<SubscriptionStateResponse>(SUBSCRIPTION_QUERY_KEY, (state) => {
        if (!state?.subscription) return state
        return {
          ...state,
          subscription: { ...state.subscription, auto_renew_enabled: input.auto_renew_enabled },
        }
      })
      return { previous }
    },
    onError: (_error, _input, context) => {
      queries.setQueryData(SUBSCRIPTION_QUERY_KEY, context?.previous)
    },
    onSuccess: (response) => {
      queries.setQueryData<SubscriptionStateResponse>(SUBSCRIPTION_QUERY_KEY, (state) => {
        if (!state?.subscription) return state
        return {
          ...state,
          subscription: { ...state.subscription, auto_renew_enabled: response.auto_renew_enabled },
        }
      })
    },
    onSettled: () => queries.invalidateQueries({ queryKey: SUBSCRIPTION_QUERY_KEY }),
  })
}
