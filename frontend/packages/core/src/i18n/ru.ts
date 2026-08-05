export const ru = {
  'common.loading': 'Загрузка',
  'common.error': 'Что-то пошло не так',
  'common.retry': 'Повторить',
  'common.language': 'Язык',
  'common.theme': 'Тема',
  'home.title': 'Re:Pibot',
  'home.subtitle': 'Магазин ещё готовится',
} as const

export type TranslationKey = keyof typeof ru
