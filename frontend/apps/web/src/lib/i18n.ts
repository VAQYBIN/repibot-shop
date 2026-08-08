'use client'

import {
  errorMessageKey,
  type Language,
  type TranslationKey,
  translate,
  useMe,
} from '@repibot/core'
import { useCallback, useEffect } from 'react'

import { useBrowserPreferences } from './browser-preferences'

/**
 * Язык интерфейса до входа: профиля ещё нет, брать его неоткуда, кроме
 * настроек браузера.
 *
 * Определение отложено до монтирования намеренно. На сервере предпочтений
 * браузера нет, и если считать их прямо в рендере, разметка сервера и клиента
 * разойдутся — React выбросит первый рендер и залогирует ошибку гидратации.
 * Поэтому первый кадр всегда русский, как и `lang` в корневой разметке.
 */
export function useBrowserLanguage(): Language {
  const { language } = useBrowserPreferences()
  useDocumentLanguage(language)
  return language
}

/**
 * Язык кабинета: в профиле он выбран осознанно и важнее настроек браузера.
 * Пока профиль не загрузился, подписи берутся по языку браузера.
 */
export function useProfileLanguage(): Language {
  const { language: browser } = useBrowserPreferences()
  const me = useMe()
  const language = me.data?.language ?? browser
  useDocumentLanguage(language)
  return language
}

function useDocumentLanguage(language: Language): void {
  useEffect(() => {
    document.documentElement.lang = language
  }, [language])
}

export type Translate = (key: TranslationKey) => string

/** Функция стабильна между рендерами: её кладут в зависимости эффектов. */
export function useTranslate(language: Language): Translate {
  return useCallback((key: TranslationKey) => translate(language, key), [language])
}

/**
 * Ошибка запроса → фраза для человека.
 *
 * Мутации из `@repibot/core` бросают готовый `Error`, а прямые вызовы `api`
 * возвращают тело ответа с кодом. Обе формы приходят в одни и те же места,
 * поэтому разбираются здесь, а не в каждой странице.
 */
export function errorText(error: unknown, language: Language): string {
  if (error instanceof Error && error.message !== '') return error.message
  const code = (error as { error?: { code?: string } } | undefined)?.error?.code
  return translate(language, errorMessageKey(code))
}
