import { en } from './en'
import { ru, type TranslationKey } from './ru'

export type Language = 'ru' | 'en'
export type { TranslationKey }
export { en, ru }

const DICTIONARIES: Record<Language, Record<TranslationKey, string>> = { ru, en }
const SUPPORTED: readonly Language[] = ['ru', 'en']
const FALLBACK: Language = 'ru'

export function translate(language: Language, key: TranslationKey): string {
  return DICTIONARIES[language][key]
}

/**
 * Выбирает первый поддерживаемый язык из списка предпочтений.
 * Принимает коды как с регионом (ru-RU), так и без.
 */
export function detectLanguage(candidates: readonly string[]): Language {
  for (const candidate of candidates) {
    const code = candidate.toLowerCase().split('-')[0]
    const match = SUPPORTED.find((language) => language === code)
    if (match) return match
  }
  return FALLBACK
}
