import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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

const ORDERS_QUERY_KEY = ['orders'] as const
const SUBSCRIPTION_QUERY_KEY = ['subscription'] as const
const GIFTS_QUERY_KEY = ['gifts'] as const

export function useOrders() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ORDERS_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/orders')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/orders')
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
