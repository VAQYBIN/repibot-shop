import { describe, expect, it } from 'vitest'

import { en } from './en'
import { detectLanguage, translate } from './index'
import { ru } from './ru'

describe('переводы', () => {
  it('возвращает строку выбранного языка', () => {
    expect(translate('ru', 'common.loading')).toBe(ru['common.loading'])
    expect(translate('en', 'common.loading')).toBe(en['common.loading'])
  })

  it('английский словарь покрывает все ключи русского', () => {
    /* Пропущенный ключ иначе всплывёт у пользователя как строка вида
       common.loading вместо текста. */
    expect(Object.keys(en).sort()).toEqual(Object.keys(ru).sort())
  })

  it('ни одно значение не пустое', () => {
    for (const [key, value] of Object.entries({ ...ru, ...en })) {
      expect(value.trim(), `пустой перевод: ${key}`).not.toBe('')
    }
  })
})

describe('определение языка', () => {
  it('берёт первый поддерживаемый из списка', () => {
    expect(detectLanguage(['de-DE', 'en-US', 'ru'])).toBe('en')
  })

  it('понимает код с регионом', () => {
    expect(detectLanguage(['ru-RU'])).toBe('ru')
  })

  it('падает обратно на русский, когда ничего не подходит', () => {
    expect(detectLanguage(['de', 'fr'])).toBe('ru')
  })

  it('переживает пустой список', () => {
    expect(detectLanguage([])).toBe('ru')
  })
})
