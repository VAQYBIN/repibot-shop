/**
 * Мост между активностью Mini App и кэшем запросов.
 *
 * Кэш сам умеет узнавать о возвращении только по видимости документа, а
 * свёрнутый Mini App для страницы остаётся видимым. Без этого моста человек,
 * вернувшийся с формы провайдера, видел бы состояние, снятое до оплаты.
 */

import { focusManager } from '@tanstack/react-query'

import { watchTelegramActivity } from './telegram'

export function trackTelegramActivity(): void {
  focusManager.setEventListener((setFocused) => watchTelegramActivity(setFocused))
}
