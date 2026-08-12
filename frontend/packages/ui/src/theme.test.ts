import { readdirSync, readFileSync } from 'node:fs'
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

function blockAfter(marker: string, selector: string): string {
  const markerIndex = css.indexOf(marker)
  expect(markerIndex, `в theme.css нет ${marker}`).toBeGreaterThanOrEqual(0)
  const selectorIndex = css.indexOf(`${selector} {`, markerIndex)
  expect(selectorIndex, `после ${marker} нет блока ${selector}`).toBeGreaterThanOrEqual(0)
  const opening = css.indexOf('{', selectorIndex)
  let depth = 1
  for (let index = opening + 1; index < css.length; index += 1) {
    if (css[index] === '{') depth += 1
    if (css[index] === '}') depth -= 1
    if (depth === 0) return css.slice(opening + 1, index)
  }
  throw new Error(`блок ${selector} не закрыт`)
}

function tokens(source: string): Record<string, string> {
  return Object.fromEntries(
    [...source.matchAll(/(--rp-[\w-]+):\s*([^;]+);/g)].map((match) => [
      match[1] ?? '',
      (match[2] ?? '').trim().toLowerCase(),
    ]),
  )
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

  it('до гидратации системная dark-тема получает тот же набор токенов', () => {
    const fallback = blockAfter('@media (prefers-color-scheme: dark)', ':root:not([data-theme])')
    expect(tokens(fallback)).toEqual(tokens(block('[data-theme="dark"]')))
  })

  it('токены Tailwind ссылаются на переменные, а не на значения', () => {
    expect(css).toContain('@theme inline')
    expect(css).toContain('--color-accent: var(--rp-accent)')
  })
})

/**
 * Раздел 5 бренд-бука. Начертание в таблицу намеренно не входит: оно
 * ставится классом на месте, иначе `font-weight` из токена спорит с
 * `font-medium` на кнопке, и исход решает порядок правил в собранном файле.
 */
const TYPE_SCALE: Record<string, readonly [string, string, string]> = {
  display: ['48px', '1.1', '-0.02em'],
  h1: ['32px', '1.2', '-0.02em'],
  h2: ['24px', '1.3', '-0.01em'],
  h3: ['19px', '1.4', '0'],
  body: ['16px', '1.6', '0'],
  small: ['14px', '1.5', '0'],
  caption: ['12px', '1.4', '0.01em'],
}

describe('шкала кеглей', () => {
  it.each(Object.entries(TYPE_SCALE))('%s объявлен целиком', (name, [size, height, tracking]) => {
    expect(css).toContain(`--text-${name}: ${size};`)
    expect(css).toContain(`--text-${name}--line-height: ${height};`)
    expect(css).toContain(`--text-${name}--letter-spacing: ${tracking};`)
  })

  it('встроенная шкала погашена, и погашена раньше своей', () => {
    const kill = css.indexOf('--text-*: initial')
    expect(kill, 'встроенные размеры не погашены').toBeGreaterThanOrEqual(0)
    // Порядок значим: `initial` после своих имён снесло бы и их тоже.
    expect(kill).toBeLessThan(css.indexOf('--text-display:'))
  })

  it('начертание в шкалу не входит', () => {
    expect(css).not.toMatch(/--text-[a-z0-9]+--font-weight/)
  })
})

describe('движение', () => {
  it('объявлено тремя переменными', () => {
    expect(css).toContain('--rp-motion-fast: 150ms')
    expect(css).toContain('--rp-motion: 200ms')
    expect(css).toContain('--rp-ease: cubic-bezier(0.2, 0, 0, 1)')
  })

  it('переходы Tailwind по умолчанию берут наши значения', () => {
    // Без этих двух строк каждый компонент писал бы длительность руками,
    // и первый же забытый `duration-` вышел бы из системы незаметно.
    expect(css).toContain('--default-transition-duration: var(--rp-motion-fast)')
    expect(css).toContain('--default-transition-timing-function: var(--rp-ease)')
  })

  it('настройка системы гасит длительности одним правилом', () => {
    const reduced = blockAfter('@media (prefers-reduced-motion: reduce)', ':root')
    expect(reduced).toContain('--rp-motion-fast: 0ms')
    expect(reduced).toContain('--rp-motion: 0ms')
  })
})

/** Имена, погашенные строкой `--text-*: initial` в theme.css. */
const RETIRED = [
  'xs',
  'sm',
  'base',
  'lg',
  'xl',
  '2xl',
  '3xl',
  '4xl',
  '5xl',
  '6xl',
  '7xl',
  '8xl',
  '9xl',
]

const ROOTS = [
  resolve(process.cwd(), 'src'),
  resolve(process.cwd(), '../../apps/web/src'),
  resolve(process.cwd(), '../../apps/miniapp/src'),
]

function sources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = resolve(directory, entry.name)
    if (entry.isDirectory()) return sources(full)
    return /\.(tsx?|css)$/.test(entry.name) ? [full] : []
  })
}

/**
 * Гасит комментарии перед поиском класса, а не наоборот: в theme.css есть
 * поясняющий комментарий, где `text-sm` упомянут как пример в прозе, а не
 * как класс. Искать «класс только рядом с className/cn(/.selector» здесь не
 * получится честно — в button.tsx кегль лежит в объекте варианта cva()
 * без этих меток на той же строке, и такое правило било бы мимо настоящих
 * находок. Замена символов на пробелы (а не удаление) сохраняет номера строк,
 * чтобы список из сторожа указывал на реальное место.
 */
function withoutComments(text: string): string {
  const noBlock = text.replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, ' '))
  // Не режем `//` внутри `://`, чтобы не задеть ссылки в строках.
  return noBlock.replace(/(?<!:)\/\/.*$/gm, '')
}

describe('шкала кеглей заперта', () => {
  /* Погашенный класс не ломает сборку: Tailwind молча ничего для него не
     выпускает, и текст остаётся унаследованного размера. Заметить это на
     глаз можно не всегда — поэтому сторож. */
  it('во всех исходниках не осталось встроенных имён кегля', () => {
    const pattern = new RegExp(`\\btext-(${RETIRED.join('|')})\\b`)
    const guilty: string[] = []

    for (const root of ROOTS) {
      for (const file of sources(root)) {
        const line = withoutComments(readFileSync(file, 'utf8'))
          .split('\n')
          .findIndex((text) => pattern.test(text))
        if (line >= 0) guilty.push(`${file}:${line + 1}`)
      }
    }

    expect(guilty).toEqual([])
  })
})

describe('границы называют существующую ступень', () => {
  /* Ступеней у границы две — subtle и strong, — и токена `--color-border`
     без ступени нет. Класс `border-border` из-за этого не выпускается вовсе:
     цвет молча наследуется от currentColor, то есть граница красится текстом.
     На светлой теме это выглядит просто как линия потемнее, поэтому глазом
     ловится плохо, а имя напрашивается само — отсюда сторож.

     Именно так въехали шапка и подвал публичных страниц. */
  it('в theme.css нет токена границы без ступени', () => {
    expect(css).not.toMatch(/--color-border:\s/)
  })

  it('во всех исходниках граница названа со ступенью', () => {
    /* Имя собирается из частей, иначе сторож находит сам себя: буквальное
       написание искомого класса в этом же файле — тоже совпадение. */
    const border = 'border'
    const pattern = new RegExp(`\\b${border}-${border}(?![-\\w])`)
    const guilty: string[] = []

    for (const root of ROOTS) {
      for (const file of sources(root)) {
        const line = withoutComments(readFileSync(file, 'utf8'))
          .split('\n')
          .findIndex((text) => pattern.test(text))
        if (line >= 0) guilty.push(`${file}:${line + 1}`)
      }
    }

    expect(guilty).toEqual([])
  })
})
