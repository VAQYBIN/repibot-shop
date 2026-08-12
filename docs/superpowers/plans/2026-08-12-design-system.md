# Слой системы: шкала, плотность, движение, знак

> **Для исполнителя:** план выполняется задача за задачей. Шаги помечены `- [ ]`.

**Цель:** заменить произвольные кегли Tailwind шкалой бренд-бука, задать плотность и движение токенами, добавить обёртку иконок, прелоадер и скелетон.

**Устройство:** всё живёт в `frontend/packages/ui`. Сначала правится `theme.css` — он один источник правды о размерах, — затем на новую шкалу переводятся восемь уже написанных компонентов пакета, затем добавляются три новых. Ни одно приложение в этом плане не трогается.

**Стек:** Tailwind 4, React 19, vitest, `@hugeicons/react` и `@hugeicons/core-free-icons`.

## Общие ограничения

- **Ветка `dev`.** Никаких git-команд: коммиты делает ведущий после проверки задачи.
- **Никакого `uv run check`** и никакого `pnpm biome check` по всему пакету: рядом работают соседи, их незаконченный код всегда красный. Запускать только тесты своего пакета.
- **Зависимости уже установлены.** `package.json` и `pnpm-lock.yaml` не трогать.
- **Комментарии по-русски и о том, почему**, а не о том, что делает строка. Очевидное не комментировать.
- **Никаких `// biome-ignore` без сработавшего правила.** Неиспользуемое подавление само роняет проверку.
- Значения кеглей, интерлиньяжа и трекинга — из `docs/design/repibot-brandbook.md`, раздел 5. Сверять по документу, не по памяти.
- Тесты запускаются из `frontend/packages/ui`: `pnpm vitest run <файл>`.

## Карта файлов

| Файл | Ответственность |
|---|---|
| `src/theme.css` | Токены: цвет, шкала кеглей, движение, ключевые кадры знака |
| `src/theme.test.ts` | Сторож токенов: правка «на глаз» не проходит молча |
| `src/components/icon.tsx` | Обёртка над Hugeicons: три размера, одна толщина обводки |
| `src/components/spinner.tsx` | Прелоадер: вращается спираль, ядро стоит |
| `src/components/skeleton.tsx` | Заглушка формы будущего содержимого |
| `src/components/logo-mark.tsx` | Знак; получает режим вращения — геометрия остаётся в одном файле |
| `src/components/card.tsx` | Карточка: плотность и отказ от тени |
| `src/index.ts` | Публичный экспорт пакета |

---

### Задача 1: Шкала кеглей

**Файлы:**
- Изменить: `frontend/packages/ui/src/theme.css` (блок `@theme inline`, строки 129–161)
- Изменить: `frontend/packages/ui/src/theme.test.ts`

**Интерфейсы:**
- Отдаёт: утилиты `text-display`, `text-h1`, `text-h2`, `text-h3`, `text-body`, `text-small`, `text-caption`. Всеми последующими планами используются только они.

- [ ] **Шаг 1: Написать падающий тест**

В конец `src/theme.test.ts`, отдельным `describe`:

```ts
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
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/theme.test.ts`
Ожидается: падение на `--text-display: 48px;` — такой строки в файле нет.

- [ ] **Шаг 3: Объявить шкалу**

В `src/theme.css`, внутри `@theme inline`, сразу после блока `--font-mono`:

```css
  /* Встроенные размеры Tailwind гасятся целиком. Пока `text-sm` продолжает
     работать, о кеглях существуют два источника правды, и побеждает тот,
     который короче пишется. Строка обязана стоять до объявления своих имён:
     `initial` действует на всё пространство имён разом. */
  --text-*: initial;

  /* Раздел 5 бренд-бука. Начертание сюда не входит — оно ставится классом
     на месте: `font-weight` из токена спорит с `font-medium`, и спор решает
     порядок правил в собранном файле, а не порядок классов в разметке. */
  --text-display: 48px;
  --text-display--line-height: 1.1;
  --text-display--letter-spacing: -0.02em;

  --text-h1: 32px;
  --text-h1--line-height: 1.2;
  --text-h1--letter-spacing: -0.02em;

  --text-h2: 24px;
  --text-h2--line-height: 1.3;
  --text-h2--letter-spacing: -0.01em;

  --text-h3: 19px;
  --text-h3--line-height: 1.4;
  --text-h3--letter-spacing: 0;

  --text-body: 16px;
  --text-body--line-height: 1.6;
  --text-body--letter-spacing: 0;

  --text-small: 14px;
  --text-small--line-height: 1.5;
  --text-small--letter-spacing: 0;

  --text-caption: 12px;
  --text-caption--line-height: 1.4;
  --text-caption--letter-spacing: 0.01em;
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/theme.test.ts`
Ожидается: все проверки шкалы зелёные, старые проверки токенов цвета — тоже.

---

### Задача 2: Токены движения

**Файлы:**
- Изменить: `frontend/packages/ui/src/theme.css`
- Изменить: `frontend/packages/ui/src/theme.test.ts`

**Интерфейсы:**
- Потребляет: ничего.
- Отдаёт: `--rp-motion-fast`, `--rp-motion`, `--rp-ease`. Классы `transition-colors` и `transition` во всех компонентах начинают подчиняться им без единой правки на месте — длительность по умолчанию переопределена в теме.

- [ ] **Шаг 1: Написать падающий тест**

В `src/theme.test.ts`, отдельным `describe`:

```ts
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
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/theme.test.ts`
Ожидается: падение на `--rp-motion-fast: 150ms`.

- [ ] **Шаг 3: Объявить движение**

В `src/theme.css`, в блоке `:root`, после теней и перед `--rp-overlay`:

```css
  /* Служебное движение: подсветка при наведении и появление слоёв. Кривая
     без разгона на выходе — плотный интерфейс не должен пружинить. */
  --rp-motion-fast: 150ms;
  --rp-motion: 200ms;
  --rp-ease: cubic-bezier(0.2, 0, 0, 1);
```

Сразу после закрывающей скобки блока `@media (prefers-color-scheme: dark)` — новый блок:

```css
/* Одно правило на весь интерфейс. Оговорка в каждом компоненте по отдельности
   держалась бы ровно до первого забытого компонента. */
@media (prefers-reduced-motion: reduce) {
  :root {
    --rp-motion-fast: 0ms;
    --rp-motion: 0ms;
  }
}
```

В блоке `@theme inline`, после объявления шкалы кеглей:

```css
  --default-transition-duration: var(--rp-motion-fast);
  --default-transition-timing-function: var(--rp-ease);
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/theme.test.ts`
Ожидается: PASS.

---

### Задача 3: Плотность карточки

**Файлы:**
- Изменить: `frontend/packages/ui/src/components/card.tsx`
- Создать: `frontend/packages/ui/src/components/card.test.tsx`

**Интерфейсы:**
- Отдаёт: `Card` без тени, с внутренним отступом 20px и радиусом 10px. Экранные планы полагаются на то, что карточка сама по себе плоская, и тень к ней не добавляют.

- [ ] **Шаг 1: Написать падающий тест**

Создать `src/components/card.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Card } from './card'

describe('Card', () => {
  it('рендерит содержимое', () => {
    render(<Card>Подписка</Card>)

    expect(screen.getByText('Подписка')).toBeInTheDocument()
  })

  it('плоская: иерархию держат граница и фон, а не тень', () => {
    /* Тень остаётся только у того, что действительно висит над страницей:
       диалог, выпадающее меню, подсказка. Карточка лежит в потоке. */
    const { container } = render(<Card>Подписка</Card>)

    expect(container.firstElementChild?.className).not.toContain('shadow')
  })

  it('плотная: отступ 20px и средний радиус', () => {
    const { container } = render(<Card>Подписка</Card>)
    const classes = container.firstElementChild?.className.split(' ') ?? []

    expect(classes).toContain('p-5')
    expect(classes).toContain('rounded-md')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/card.test.tsx`
Ожидается: падение на проверке тени — сейчас в классах `shadow-[var(--rp-shadow-sm)]`.

- [ ] **Шаг 3: Убрать тень и уплотнить**

В `src/components/card.tsx` заменить строку классов на:

```tsx
        'rounded-md border border-border-subtle bg-surface p-5',
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/card.test.tsx`
Ожидается: PASS.

---

### Задача 4: Перевод компонентов пакета на шкалу

**Файлы:**
- Изменить: `frontend/packages/ui/src/components/button.tsx:20-22`
- Изменить: `frontend/packages/ui/src/components/dialog.tsx:96,100`
- Изменить: `frontend/packages/ui/src/components/empty-state.tsx:24`
- Изменить: `frontend/packages/ui/src/components/form-field.tsx:47,52,57`
- Изменить: `frontend/packages/ui/src/components/switch.tsx:58`

**Интерфейсы:**
- Потребляет: шкалу из задачи 1.
- Отдаёт: пакет, в котором не осталось ни одного погашенного имени кегля. Это условие проверяется сторожем в самом конце подпроекта, но начинается здесь.

Ровно десять мест. Соответствие:

| Было | Стало | Где |
|---|---|---|
| `text-sm` | `text-small` | button `sm`, dialog:100, empty-state:24, form-field:47,52,57, switch:58 |
| `text-base` | `text-body` | button `md` |
| `text-lg` | `text-h3` | button `lg`, dialog:96 |

- [ ] **Шаг 1: Убедиться, что тесты сейчас зелёные**

Запустить: `pnpm vitest run`
Ожидается: PASS. Это исходное состояние — правка не должна его изменить.

- [ ] **Шаг 2: Заменить кегли**

`button.tsx`, размеры:

```tsx
      size: {
        sm: 'h-8 px-3 text-small rounded-sm',
        md: 'h-10 px-4 text-body rounded-md',
        lg: 'h-12 px-6 text-h3 rounded-md',
      },
```

`dialog.tsx:96` — `className="text-h3 font-semibold text-text"`.
`dialog.tsx:100` — `className="mt-2 text-small text-text-secondary"`.
`empty-state.tsx:24` — `className="text-small text-text-secondary"`.
`form-field.tsx:47` — `className="text-small font-medium text-text"`.
`form-field.tsx:52` — `className="text-small text-text-muted"`.
`form-field.tsx:57` — `className="text-small text-danger"`.
`switch.tsx:58` — `className="text-small text-text"`.

- [ ] **Шаг 3: Убедиться, что ни одного погашенного имени не осталось**

Запустить: `grep -rn "text-\(xs\|sm\|base\|lg\|xl\|2xl\|3xl\)" src/`
Ожидается: пустой вывод.

- [ ] **Шаг 4: Убедиться, что тесты по-прежнему зелёные**

Запустить: `pnpm vitest run`
Ожидается: PASS. Тест кнопки проверяет цвета и вариант `sm`, размеров не касается, поэтому падений быть не должно. Если что-то упало — правка задела не то.

---

### Задача 5: Обёртка иконок

**Файлы:**
- Создать: `frontend/packages/ui/src/components/icon.tsx`
- Создать: `frontend/packages/ui/src/components/icon.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт:

```tsx
export type { IconSvgElement } from '@hugeicons/react'

export interface IconProps {
  icon: IconSvgElement
  size?: 16 | 20 | 24
  className?: string | undefined
  title?: string | undefined
}

export function Icon(props: IconProps): JSX.Element
```

Все планы экранов берут иконки только через неё. Названия иконок — из `@hugeicons/core-free-icons`; перед использованием сверять имя по `node_modules/@hugeicons/core-free-icons/dist/index.d.ts`, наугад не писать.

- [ ] **Шаг 1: Написать падающий тест**

Создать `src/components/icon.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Icon } from './icon'

/* Своя геометрия вместо настоящей иконки: тест про обёртку, а не про
   содержимое пакета, и от смены набора иконок он зависеть не должен. */
const SQUARE = [['path', { d: 'M4 4h16v16H4z' }]] as const

describe('Icon', () => {
  it('без названия иконка декоративна и от скринридера скрыта', () => {
    const { container } = render(<Icon icon={SQUARE} />)
    const svg = container.querySelector('svg')

    expect(svg).toHaveAttribute('aria-hidden', 'true')
    expect(svg).not.toHaveAttribute('role', 'img')
  })

  it('с названием иконка становится картинкой с подписью', () => {
    render(<Icon icon={SQUARE} title="Устройства" />)

    expect(screen.getByRole('img', { name: 'Устройства' })).toBeInTheDocument()
  })

  it('размер по умолчанию — 20', () => {
    const { container } = render(<Icon icon={SQUARE} />)

    expect(container.querySelector('svg')).toHaveAttribute('width', '20')
  })

  it('размер задаётся явно', () => {
    const { container } = render(<Icon icon={SQUARE} size={24} />)

    expect(container.querySelector('svg')).toHaveAttribute('width', '24')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/icon.test.tsx`
Ожидается: падение на разрешении `./icon` — файла нет.

- [ ] **Шаг 3: Написать обёртку**

Создать `src/components/icon.tsx`:

```tsx
import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react'

export type { IconSvgElement }

export interface IconProps {
  icon: IconSvgElement
  /** 16 — рядом с мелким текстом, 20 — обычный, 24 — самостоятельная кнопка. */
  size?: 16 | 20 | 24
  className?: string | undefined
  /**
   * Название для скринридера. Без него иконка декоративна — и это верно
   * для подавляющего большинства мест, где рядом есть подпись словами.
   */
  title?: string | undefined
}

/**
 * Единственный вход к иконкам.
 *
 * Толщина обводки одна на все размеры: разнобой заметен, когда иконки стоят
 * рядом в меню. Цвет не задаётся вовсе — иконка наследует цвет текста, поэтому
 * отдельного токена под иконки в палитре нет и не нужно.
 */
export function Icon({ icon, size = 20, className, title }: IconProps) {
  const label = title === undefined ? { 'aria-hidden': true } : { role: 'img', 'aria-label': title }
  return (
    <HugeiconsIcon
      icon={icon}
      size={size}
      strokeWidth={1.5}
      color="currentColor"
      className={className}
      {...label}
    />
  )
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/icon.test.tsx`
Ожидается: PASS. Если `width` на svg не оказалось — посмотреть, как `HugeiconsIcon` раскладывает `size`, и поправить проверку под действительность, а не действительность под проверку.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, по алфавиту между `FormField` и `Input`:

```ts
export { Icon, type IconProps, type IconSvgElement } from './components/icon'
```

---

### Задача 6: Прелоадер

**Файлы:**
- Изменить: `frontend/packages/ui/src/components/logo-mark.tsx`
- Изменить: `frontend/packages/ui/src/theme.css`
- Создать: `frontend/packages/ui/src/components/spinner.tsx`
- Создать: `frontend/packages/ui/src/components/spinner.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Потребляет: `LogoMark` с его геометрией.
- Отдаёт: `Spinner({ size?: number, label?: string })`. Все экранные планы заменяют им надписи «Загрузка…».

Раздел 6 бренд-бука: вращается спираль, ядро стоит, 1.4с, `linear`. Центр вращения — центр ядра: `54.5 42.5` у полной версии знака и `62.5 38.5` у малой. Это же центр дуг спирали — совпадение не случайно, так построена геометрия.

- [ ] **Шаг 1: Написать падающий тест**

Создать `src/components/spinner.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Spinner } from './spinner'

describe('Spinner', () => {
  it('объявляет о себе как о состоянии', () => {
    render(<Spinner label="Загрузка подписки" />)

    expect(screen.getByRole('status', { name: 'Загрузка подписки' })).toBeInTheDocument()
  })

  it('вращается только обводка, ядро остаётся неподвижным', () => {
    /* Раздел 6 бренд-бука. Если класс уедет на весь знак, ядро начнёт
       обходить круг по орбите — это прямо запрещено. */
    const { container } = render(<Spinner />)

    expect(container.querySelector('path')).toHaveClass('rp-mark-spin')
    expect(container.querySelector('circle')).not.toHaveClass('rp-mark-spin')
  })

  it('ниже 32px берётся малая версия знака', () => {
    /* Раздел 4 бренд-бука запрещает решать слипание витков уменьшением
       полной версии. У малой другой viewBox — по нему и проверяем. */
    const { container } = render(<Spinner size={20} />)

    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 101 89')
  })

  it('от 32px берётся полная версия', () => {
    const { container } = render(<Spinner size={48} />)

    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 109 97')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/spinner.test.tsx`
Ожидается: падение на разрешении `./spinner`.

- [ ] **Шаг 3: Научить знак вращаться**

В `src/components/logo-mark.tsx` добавить в `LogoMarkProps`:

```tsx
  /**
   * Вращение спирали при неподвижном ядре — фирменный прелоадер из раздела 6
   * бренд-бука. Режим живёт здесь, а не в `Spinner`, потому что центр
   * вращения — часть геометрии знака, а геометрия заперта в этом файле.
   */
  spinning?: boolean | undefined
```

И в теле компонента:

```tsx
export function LogoMark({
  variant = 'full',
  title = 'Re:Pibot',
  spinning,
  ...props
}: LogoMarkProps) {
  const mark = MARKS[variant]
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox={mark.viewBox} fill="none" {...props}>
      <title>{title}</title>
      <path
        d={mark.path}
        stroke="currentColor"
        strokeWidth={mark.strokeWidth}
        strokeLinecap="round"
        className={spinning ? 'rp-mark-spin' : undefined}
        style={
          spinning
            ? ({ '--rp-mark-origin': `${mark.core.cx}px ${mark.core.cy}px` } as CSSProperties)
            : undefined
        }
      />
      <circle cx={mark.core.cx} cy={mark.core.cy} r={mark.core.r} fill="var(--rp-accent)" />
    </svg>
  )
}
```

Импорт типа: `import type { CSSProperties, SVGProps } from 'react'`.

- [ ] **Шаг 4: Описать вращение в теме**

В конец `src/theme.css`:

```css
/* Прелоадер бренд-бука, раздел 6: вращается спираль, ядро стоит.
   `view-box` обязателен — при `fill-box` начало координат уехало бы в угол
   рамки самой дуги, и знак завертелся бы вокруг случайной точки. */
@keyframes rp-mark-spin {
  to {
    transform: rotate(1turn);
  }
}

.rp-mark-spin {
  animation: rp-mark-spin 1.4s linear infinite;
  transform-origin: var(--rp-mark-origin);
  transform-box: view-box;
}

/* Замедляется втрое, а не останавливается: неподвижный прелоадер перестаёт
   сообщать, что работа идёт, и человек решает, что всё зависло. */
@media (prefers-reduced-motion: reduce) {
  .rp-mark-spin {
    animation-duration: 4.2s;
  }
}
```

- [ ] **Шаг 5: Написать прелоадер**

Создать `src/components/spinner.tsx`:

```tsx
import { LogoMark } from './logo-mark'

export interface SpinnerProps {
  /** Сторона в пикселях. По умолчанию 24 — размер строки текста рядом. */
  size?: number
  /** Что именно грузится. Читается скринридером вместо картинки. */
  label?: string
  className?: string | undefined
}

/** Ниже этого размера полный знак слипается — раздел 4 бренд-бука. */
const SMALL_BELOW = 32

export function Spinner({ size = 24, label = 'Загрузка', className }: SpinnerProps) {
  return (
    <span role="status" aria-label={label} className={className}>
      <LogoMark
        variant={size < SMALL_BELOW ? 'small' : 'full'}
        spinning
        title={label}
        width={size}
        height={size}
        className="text-text-muted"
      />
    </span>
  )
}
```

- [ ] **Шаг 6: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/spinner.test.tsx src/components/logo-mark.test.tsx`
Ожидается: PASS обоих файлов. Тест знака трогать нельзя — новый режим по умолчанию выключен, и старое поведение обязано остаться прежним.

- [ ] **Шаг 7: Выставить наружу**

В `src/index.ts`, после `PasswordInput`:

```ts
export { Spinner, type SpinnerProps } from './components/spinner'
```

---

### Задача 7: Скелетон

**Файлы:**
- Создать: `frontend/packages/ui/src/components/skeleton.tsx`
- Создать: `frontend/packages/ui/src/components/skeleton.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт: `Skeleton({ className })`. Экранные планы ставят его там, где форма будущего содержимого известна заранее — строки таблицы, карточка подписки. Где не известна — ставят `Spinner`.

- [ ] **Шаг 1: Написать падающий тест**

Создать `src/components/skeleton.test.tsx`:

```tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Skeleton } from './skeleton'

describe('Skeleton', () => {
  it('от скринридера скрыт', () => {
    /* Заглушка не содержит сведений. Объявлять её вслух — значит читать
       человеку пустоту; о загрузке сообщает Spinner или role=status рядом. */
    const { container } = render(<Skeleton />)

    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
  })

  it('принимает форму снаружи', () => {
    const { container } = render(<Skeleton className="h-10 w-full" />)
    const classes = container.firstElementChild?.className.split(' ') ?? []

    expect(classes).toContain('h-10')
    expect(classes).toContain('w-full')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/skeleton.test.tsx`
Ожидается: падение на разрешении `./skeleton`.

- [ ] **Шаг 3: Написать скелетон**

Создать `src/components/skeleton.tsx`:

```tsx
import { cn } from '../lib/cn'

export interface SkeletonProps {
  className?: string | undefined
}

/**
 * Заглушка на месте будущего содержимого.
 *
 * Размеров у неё своих нет: их задаёт место применения, потому что смысл
 * скелетона именно в том, чтобы повторить форму того, что появится. Пульсация
 * гаснет вместе с остальным движением — за это отвечает `motion-safe`.
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn('rounded-md bg-surface-sunken motion-safe:animate-pulse', className)}
    />
  )
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/skeleton.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, после `Skeleton` по алфавиту — то есть между `PasswordInput` и `Spinner`:

```ts
export { Skeleton, type SkeletonProps } from './components/skeleton'
```

- [ ] **Шаг 6: Прогнать пакет целиком**

Запустить: `pnpm vitest run && pnpm typecheck`
Ожидается: PASS обеих команд. Это последняя задача плана — пакет должен быть целым.
