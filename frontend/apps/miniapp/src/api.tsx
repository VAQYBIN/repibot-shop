import { createTokenStore, detectLanguage, type Language, useMe } from '@repibot/core'

import { preferredLanguages } from './telegram'

/**
 * Базовый URL пустой: MiniApp и API стоят за одним nginx, а абсолютный адрес
 * в сборке потребовал бы пересборки под каждое развёртывание.
 */
export const API_BASE_URL = ''

/**
 * Хранилище токена — один экземпляр на приложение, а не часть провайдера:
 * токен в него кладёт обмен initData, который случается до отрисовки React.
 * Готовое хранилище принимает AuthProvider из @repibot/core, поэтому свой
 * клиент и свои копии хуков MiniApp не заводит.
 */
export const tokenStore = createTokenStore()

/**
 * Язык интерфейса. Сохранённый в профиле важнее предпочтений Telegram
 * и браузера: пользователь выбрал его сам.
 *
 * Хук подходит только экранам, которым профиль и так нужен: он подписывается
 * на тот же запрос и до входа сходил бы в API без токена.
 */
export function useLanguage(): Language {
  const profile = useMe()
  return profile.data?.language ?? detectLanguage(preferredLanguages())
}
