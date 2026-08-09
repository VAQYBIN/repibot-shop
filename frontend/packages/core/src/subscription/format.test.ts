import { describe, expect, it } from 'vitest'

import { formatBytes, formatDate } from './format'

describe('formatBytes', () => {
  it('показывает безлимит отдельным случаем', () => {
    // Ноль в панели означает «без ограничения», а не «нисколько».
    expect(formatBytes(0, 'ru', { zeroIsUnlimited: true })).toBe('∞')
  })

  it('округляет до одного знака и не пишет дробь у байт', () => {
    expect(formatBytes(512, 'ru')).toBe('512 Б')
    expect(formatBytes(1536, 'ru')).toBe('1,5 КБ')
    expect(formatBytes(1_073_741_824, 'ru')).toBe('1 ГБ')
  })

  it('переводит единицы', () => {
    expect(formatBytes(1536, 'en')).toBe('1.5 KB')
  })

  it('показывает дату в локали интерфейса', () => {
    expect(formatDate('2026-09-05T12:00:00Z', 'ru')).toBe('5 сент. 2026 г.')
    expect(formatDate('2026-09-05T12:00:00Z', 'en')).toBe('Sep 5, 2026')
  })
})
