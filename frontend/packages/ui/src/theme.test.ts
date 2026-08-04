import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * Значения взяты из docs/design/repibot-brandbook.md, раздел 3.
 * Тест существует ровно затем, чтобы правка «на глаз» в CSS не прошла молча.
 */
const LIGHT_TOKENS: Record<string, string> = {
  '--rp-ink': '#1A1A18',
  '--rp-paper': '#FAF9F7',
  '--rp-jade': '#17A67C',
  '--rp-jade-deep': '#0E6B50',
  '--rp-jade-mist': '#E4F5EE',
  '--rp-bg': '#FAF9F7',
  '--rp-surface': '#FFFFFF',
  '--rp-surface-sunken': '#F1F0EC',
  '--rp-border': '#E2E1DC',
  '--rp-border-strong': '#C9C7C0',
  '--rp-text': '#1A1A18',
  '--rp-text-secondary': '#575651',
  '--rp-text-muted': '#7A7873',
  '--rp-text-accent': '#0E6B50',
  '--rp-accent': '#17A67C',
  '--rp-accent-hover': '#128A67',
  '--rp-on-accent': '#FFFFFF',
  '--rp-success': '#2F9E44',
  '--rp-warning': '#B87A0B',
  '--rp-danger': '#C0392F',
  '--rp-info': '#2B72C4',
}

const DARK_TOKENS: Record<string, string> = {
  '--rp-bg': '#121311',
  '--rp-surface': '#1C1D1B',
  '--rp-surface-sunken': '#0D0E0C',
  '--rp-border': '#2E2F2C',
  '--rp-border-strong': '#43443F',
  '--rp-text': '#F2F1ED',
  '--rp-text-secondary': '#A3A19A',
  '--rp-text-muted': '#7A7873',
  '--rp-text-accent': '#2CC694',
  '--rp-accent': '#2CC694',
  '--rp-accent-hover': '#45D6A8',
  '--rp-on-accent': '#08150F',
  '--rp-jade-mist': '#10322A',
  '--rp-success': '#51CF66',
  '--rp-warning': '#E8A32C',
  '--rp-danger': '#E8615A',
  '--rp-info': '#5AA3E8',
}

// От корня пакета, а не от import.meta.url: в окружении jsdom vitest подменяет
// его на не-file URL, и fileURLToPath на нём падает.
const css = readFileSync(resolve(process.cwd(), 'src/theme.css'), 'utf8')

/**
 * Ищем именно объявление правила в начале строки: тот же селектор встречается
 * внутри `@custom-variant dark (...)`, и поиск по первому вхождению вернул бы его.
 */
function block(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = css.match(new RegExp(`^${escaped}\\s*\\{([^}]*)\\}`, 'm'))
  expect(match, `в theme.css нет блока ${selector}`).not.toBeNull()
  return match?.[1] ?? ''
}

describe('токены бренда', () => {
  // Регистр hex не сверяем: форматтер Biome приводит его к нижнему, а бренд-бук
  // записан в верхнем. Значимо само значение цвета, а не его написание.
  const light = block(':root').toLowerCase()
  const dark = block('[data-theme="dark"]').toLowerCase()

  it.each(Object.entries(LIGHT_TOKENS))('светлая тема: %s = %s', (token, value) => {
    expect(light).toContain(`${token}: ${value}`.toLowerCase())
  })

  it.each(Object.entries(DARK_TOKENS))('тёмная тема: %s = %s', (token, value) => {
    expect(dark).toContain(`${token}: ${value}`.toLowerCase())
  })

  it('в тёмной теме акцент не остаётся основным Jade', () => {
    expect(dark).not.toContain('--rp-accent: #17a67c')
  })

  it('вариант dark объявлен через атрибут data-theme, а не класс', () => {
    expect(css).toContain('@custom-variant dark')
    expect(css).toContain('[data-theme="dark"]')
  })

  it('токены Tailwind ссылаются на переменные, а не на значения', () => {
    expect(css).toContain('@theme inline')
    expect(css).toContain('--color-accent: var(--rp-accent)')
  })
})
