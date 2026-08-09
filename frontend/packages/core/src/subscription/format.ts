import type { Language } from '../i18n/index'

const UNITS: Record<Language, readonly string[]> = {
  ru: ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'],
  en: ['B', 'KB', 'MB', 'GB', 'TB'],
}

export function formatBytes(
  bytes: number,
  language: Language,
  { zeroIsUnlimited = false }: { zeroIsUnlimited?: boolean } = {},
): string {
  if (bytes === 0 && zeroIsUnlimited) return '∞'

  const unit = Math.min(
    Math.floor(Math.log(Math.max(bytes, 1)) / Math.log(1024)),
    UNITS[language].length - 1,
  )
  const value = bytes / 1024 ** unit
  const formatted = new Intl.NumberFormat(language, {
    maximumFractionDigits: unit === 0 ? 0 : 1,
  }).format(value)

  return `${formatted} ${UNITS[language][unit]}`
}

export function formatDate(value: string | Date, language: Language): string {
  return new Intl.DateTimeFormat(language, { dateStyle: 'medium' }).format(new Date(value))
}
