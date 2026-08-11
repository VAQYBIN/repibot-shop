import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { messageFrom } from '../auth/errors'
import { useAuthClient } from '../auth/hooks'
import type { Language } from '../i18n/index'

export function usePlans() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['plans'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/plans')
      if (error || !data) throw error ?? new Error('пустой ответ /api/plans')
      return data
    },
  })
}

export function useSubscription() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['subscription'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/subscription')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/subscription')
      return data
    },
    // Пока доступ выдаётся, состояние меняется само: экран должен догнать
    // его без перезагрузки страницы.
    refetchInterval: (query) =>
      query.state.data?.subscription?.status === 'pending_provision' ? 3000 : false,
    // Срок и автопродление меняет оплата, которая идёт вне приложения; после
    // возврата снимок недостоверен, каким бы свежим он ни был.
    refetchOnWindowFocus: 'always',
  })
}

export function useActivateTrial(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/me/subscription/trial')
      if (error || !data) throw new Error(messageFrom(error, language))
      return data
    },
    onSuccess: (data) => queries.setQueryData(['subscription'], data),
  })
}

export function useDevices() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['devices'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/devices')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/devices')
      return data
    },
  })
}

export function useUnlinkDevice(language: Language) {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  return useMutation({
    mutationFn: async (hwid: string) => {
      const { error } = await api.POST('/api/me/devices/unlink', { body: { hwid } })
      if (error) throw new Error(messageFrom(error, language))
    },
    onSuccess: () => queries.invalidateQueries({ queryKey: ['devices'] }),
  })
}

export function useTraffic() {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['traffic'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/me/traffic')
      if (error || !data) throw error ?? new Error('пустой ответ /api/me/traffic')
      return data
    },
  })
}
