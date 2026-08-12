# Примитивы: восемь компонентов, которые уже написаны руками в экранах

> **Для исполнителя:** план выполняется задача за задачей. Шаги помечены `- [ ]`.

**Цель:** добавить в `packages/ui` восемь компонентов, каждый из которых сейчас существует в виде повторённой вручную разметки в нескольких экранах.

**Устройство:** три компонента с нетривиальной клавиатурой — вкладки, выпадающее меню и подсказка — берутся на Radix. Остальные пять пишутся на нативной разметке: там доступность даётся браузером бесплатно. Экраны в этом плане не трогаются — только пакет.

**Стек:** React 19, Radix UI, Tailwind 4, vitest, `@testing-library/react`.

## Общие ограничения

- **Ветка `dev`.** Никаких git-команд: коммиты делает ведущий после проверки задачи.
- **Никакого прогона проверок по всему репозиторию.** Только тесты своего пакета: `pnpm vitest run <файл>` из `frontend/packages/ui`.
- **Зависимости уже установлены** — `@radix-ui/react-tabs`, `@radix-ui/react-dropdown-menu`, `@radix-ui/react-tooltip`. `package.json` не трогать.
- **Кегли — только по шкале бренда:** `text-display`, `text-h1`, `text-h2`, `text-h3`, `text-body`, `text-small`, `text-caption`. Имена `text-sm`, `text-base`, `text-lg` и прочие встроенные погашены и молча не работают.
- **Цвета — только токенами:** `bg-surface`, `bg-surface-sunken`, `text-text`, `text-text-secondary`, `text-text-muted`, `border-border-subtle`, `border-border-strong`, `text-danger`, `text-success`, `text-warning`, `text-info`, `bg-jade-mist`, `text-text-accent`. Никаких `bg-gray-100` и `text-red-500`.
- **Иконки — только через `Icon` из этого же пакета**, не напрямую из `lucide-react` и не своим `<svg>`.
- **Тень — только у того, что висит над страницей:** выпадающее меню и подсказка её получают, всё остальное нет.
- **Комментарии по-русски и о том, почему.** Никаких `// biome-ignore` без сработавшего правила.

## Карта файлов

Все — в `frontend/packages/ui/src/components/`, каждый со своим `*.test.tsx` рядом.

| Файл | Что заменяет в экранах |
|---|---|
| `alert.tsx` | 31 самодельный абзац `role="alert"` |
| `select.tsx` | 5 неоформленных `<select>` |
| `textarea.tsx` | 4 поля, размеченных мимо `Input` |
| `badge.tsx` | крашеный текст статусов платежей, обращений, нод |
| `table.tsx` | 2 таблицы, свёрстанные вручную |
| `tabs.tsx` | переключение периодов сводки |
| `dropdown-menu.tsx` | ряд кнопок действий в карточке пользователя |
| `tooltip.tsx` | подписи к кнопкам, у которых осталась одна иконка |

Каждая задача заканчивается строкой экспорта в `src/index.ts` — файл общий, правки в нём точечные, соседних строк не касаться.

---

### Задача 1: Alert

**Файлы:**
- Создать: `frontend/packages/ui/src/components/alert.tsx`
- Создать: `frontend/packages/ui/src/components/alert.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт: `Alert({ tone, title?, children, className? })`, где `tone: 'error' | 'warning' | 'success' | 'info'`.

Роль зависит от тона: `error` получает `role="alert"` — об отказе объявляют немедленно; остальные `role="status"` — они ждут своей очереди и не перебивают человека на полуслове.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Alert } from './alert'

describe('Alert', () => {
  it('об отказе объявляет немедленно', () => {
    render(<Alert tone="error">Карта отклонена</Alert>)

    expect(screen.getByRole('alert')).toHaveTextContent('Карта отклонена')
  })

  it('об успехе объявляет в свою очередь', () => {
    /* role=status не перебивает человека на полуслове. Для успеха это верно,
       для отказа — нет: там ждать нечего. */
    render(<Alert tone="success">Оплачено</Alert>)

    expect(screen.getByRole('status')).toHaveTextContent('Оплачено')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('заголовок необязателен и не создаёт пустой строки', () => {
    const { container } = render(<Alert tone="info">Продление через три дня</Alert>)

    expect(container.querySelector('p.font-medium')).toBeNull()
  })

  it('с заголовком показывает и его, и текст', () => {
    render(
      <Alert tone="warning" title="Подписка кончается">
        Осталось два дня
      </Alert>,
    )

    expect(screen.getByText('Подписка кончается')).toBeInTheDocument()
    expect(screen.getByText('Осталось два дня')).toBeInTheDocument()
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/alert.test.tsx`
Ожидается: падение на разрешении `./alert`.

- [ ] **Шаг 3: Написать компонент**

```tsx
import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export type AlertTone = 'error' | 'warning' | 'success' | 'info'

export interface AlertProps {
  tone: AlertTone
  title?: string | undefined
  children: ReactNode
  className?: string | undefined
}

/* Подложка — тот же цвет с прозрачностью: отдельных «мягких» оттенков под
   каждый статус в палитре нет, а выдумывать их на глаз значит завести шестую
   шкалу цвета мимо бренд-бука. */
const TONES: Record<AlertTone, string> = {
  error: 'border-danger/40 bg-danger/8 text-text',
  warning: 'border-warning/40 bg-warning/8 text-text',
  success: 'border-success/40 bg-success/8 text-text',
  info: 'border-info/40 bg-info/8 text-text',
}

export function Alert({ tone, title, children, className }: AlertProps) {
  return (
    <div
      // Отказ перебивает, остальное ждёт очереди.
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn('rounded-md border px-4 py-3 text-small', TONES[tone], className)}
    >
      {title === undefined ? null : <p className="font-medium">{title}</p>}
      <div className={title === undefined ? undefined : 'mt-1 text-text-secondary'}>{children}</div>
    </div>
  )
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/alert.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts` первой строкой (по алфавиту раньше `Button`):

```ts
export { Alert, type AlertProps, type AlertTone } from './components/alert'
```

---

### Задача 2: Select

**Файлы:**
- Создать: `frontend/packages/ui/src/components/select.tsx`
- Создать: `frontend/packages/ui/src/components/select.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт: `Select(props: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean })`. Оформление совпадает с `Input`: та же высота, та же граница, то же кольцо при фокусе.

Список остаётся нативным. Своё выпадающее решает одну задачу — вид, — а ломает три: набор с клавиатуры, поведение на телефоне и работу с формой.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Select } from './select'

function Languages(props: { onChange?: (value: string) => void }) {
  return (
    <Select
      aria-label="Язык"
      defaultValue="ru"
      onChange={(event) => props.onChange?.(event.target.value)}
    >
      <option value="ru">Русский</option>
      <option value="en">English</option>
    </Select>
  )
}

describe('Select', () => {
  it('остаётся нативным списком', () => {
    render(<Languages />)

    expect(screen.getByRole('combobox', { name: 'Язык' })).toBeInTheDocument()
  })

  it('сообщает о выборе', async () => {
    const onChange = vi.fn()
    render(<Languages onChange={onChange} />)

    await userEvent.selectOptions(screen.getByRole('combobox'), 'en')

    expect(onChange).toHaveBeenCalledWith('en')
  })

  it('признак ошибки объявляется скринридеру, а не только краской', () => {
    render(
      <Select aria-label="Язык" invalid>
        <option value="ru">Русский</option>
      </Select>,
    )

    expect(screen.getByRole('combobox')).toHaveAttribute('aria-invalid', 'true')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/select.test.tsx`
Ожидается: падение на разрешении `./select`.

- [ ] **Шаг 3: Написать компонент**

```tsx
import type { SelectHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean | undefined
}

/**
 * Список остаётся нативным.
 *
 * Своё выпадающее решало бы одну задачу — вид, — и ломало бы три: набор
 * первых букв с клавиатуры, родное колесо выбора на телефоне и отправку
 * формы без обработчиков.
 */
export function Select({ className, invalid, ...props }: SelectProps) {
  return (
    <select
      aria-invalid={invalid === true ? true : undefined}
      className={cn(
        'h-10 w-full rounded-md border bg-surface px-3 text-body text-text',
        invalid === true ? 'border-danger' : 'border-border-subtle',
        'focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/select.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, между `PasswordInput` и `Skeleton`:

```ts
export { Select, type SelectProps } from './components/select'
```

---

### Задача 3: Textarea

**Файлы:**
- Создать: `frontend/packages/ui/src/components/textarea.tsx`
- Создать: `frontend/packages/ui/src/components/textarea.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт: `Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean })`.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Textarea } from './textarea'

describe('Textarea', () => {
  it('принимает текст', async () => {
    render(<Textarea aria-label="Сообщение" />)

    await userEvent.type(screen.getByRole('textbox', { name: 'Сообщение' }), 'Не открывается')

    expect(screen.getByRole('textbox')).toHaveValue('Не открывается')
  })

  it('признак ошибки объявляется скринридеру', () => {
    render(<Textarea aria-label="Сообщение" invalid />)

    expect(screen.getByRole('textbox')).toHaveAttribute('aria-invalid', 'true')
  })

  it('высота задаётся снаружи и не сбрасывается', () => {
    render(<Textarea aria-label="Сообщение" className="min-h-40" />)

    expect(screen.getByRole('textbox').className).toContain('min-h-40')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/textarea.test.tsx`
Ожидается: падение на разрешении `./textarea`.

- [ ] **Шаг 3: Написать компонент**

```tsx
import type { TextareaHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean | undefined
}

export function Textarea({ className, invalid, ...props }: TextareaProps) {
  return (
    <textarea
      aria-invalid={invalid === true ? true : undefined}
      className={cn(
        'w-full rounded-md border bg-surface px-3 py-2 text-body text-text',
        'placeholder:text-text-muted',
        invalid === true ? 'border-danger' : 'border-border-subtle',
        'focus:border-accent focus:ring-3 focus:ring-jade-mist focus:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/textarea.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, после `Switch`:

```ts
export { Textarea, type TextareaProps } from './components/textarea'
```

---

### Задача 4: Badge

**Файлы:**
- Создать: `frontend/packages/ui/src/components/badge.tsx`
- Создать: `frontend/packages/ui/src/components/badge.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт: `Badge({ tone, children, className? })`, где `tone: 'neutral' | 'success' | 'warning' | 'danger' | 'info'`.

Цвет — не единственный признак: внутри всегда стоит слово. Статус, различимый только краской, не читается ни дальтоником, ни в чёрно-белой распечатке.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Badge } from './badge'

describe('Badge', () => {
  it('показывает слово, а не только цвет', () => {
    render(<Badge tone="success">Оплачен</Badge>)

    expect(screen.getByText('Оплачен')).toBeInTheDocument()
  })

  it('разные тона различаются классами', () => {
    const { rerender, container } = render(<Badge tone="danger">Отклонён</Badge>)
    const danger = container.firstElementChild?.className

    rerender(<Badge tone="neutral">Черновик</Badge>)

    expect(container.firstElementChild?.className).not.toBe(danger)
  })

  it('не объявляет себя скринридеру отдельным элементом', () => {
    /* Бейдж — оформление слова, стоящего рядом с предметом. Своей роли у него
       нет: лишняя роль заставила бы читать «статус» перед каждой строкой. */
    const { container } = render(<Badge tone="info">Ожидает</Badge>)

    expect(container.firstElementChild).not.toHaveAttribute('role')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/badge.test.tsx`
Ожидается: падение на разрешении `./badge`.

- [ ] **Шаг 3: Написать компонент**

```tsx
import type { ReactNode } from 'react'

import { cn } from '../lib/cn'

export type BadgeTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

export interface BadgeProps {
  tone: BadgeTone
  children: ReactNode
  className?: string | undefined
}

const TONES: Record<BadgeTone, string> = {
  neutral: 'border-border-strong text-text-secondary',
  success: 'border-success/50 text-success',
  warning: 'border-warning/50 text-warning',
  danger: 'border-danger/50 text-danger',
  info: 'border-info/50 text-info',
}

/**
 * Статус словом в рамке.
 *
 * Заливки нет намеренно: в плотном списке десяток залитых плашек начинает
 * рябить сильнее, чем сами строки. Рамка отделяет статус от текста ровно
 * настолько, насколько нужно.
 */
export function Badge({ tone, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-caption',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/badge.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, между `Alert` и `Button`:

```ts
export { Badge, type BadgeProps, type BadgeTone } from './components/badge'
```

---

### Задача 5: Table

**Файлы:**
- Создать: `frontend/packages/ui/src/components/table.tsx`
- Создать: `frontend/packages/ui/src/components/table.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт шесть частей: `Table`, `TableHead`, `TableBody`, `TableRow`, `TableHeaderCell`, `TableCell`. Все принимают `className` и обычные атрибуты своего тега.

`Table` сам оборачивается в блок с горизонтальной прокруткой: широкая таблица обязана ездить внутри себя, а не таскать вбок всю страницу. Это же проверяет сквозной обход в конце подпроекта.

Чередования строк нет: на плотной таблице зебра добавляет шума больше, чем помогает вести взгляд.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from './table'

function Payments() {
  return (
    <Table caption="Платежи">
      <TableHead>
        <TableRow>
          <TableHeaderCell>Дата</TableHeaderCell>
          <TableHeaderCell>Сумма</TableHeaderCell>
        </TableRow>
      </TableHead>
      <TableBody>
        <TableRow>
          <TableCell>12 августа</TableCell>
          <TableCell>199 ₽</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  )
}

describe('Table', () => {
  it('остаётся настоящей таблицей с подписью', () => {
    render(<Payments />)

    expect(screen.getByRole('table', { name: 'Платежи' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Дата' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '199 ₽' })).toBeInTheDocument()
  })

  it('ездит вбок внутри себя, а не таскает страницу', () => {
    /* Горизонтальная прокрутка на обёртке. Если она окажется на странице,
       сквозной обход в конце подпроекта это поймает — но лучше здесь. */
    const { container } = render(<Payments />)

    expect(container.firstElementChild?.className).toContain('overflow-x-auto')
  })

  it('строки не чередуются краской', () => {
    const { container } = render(<Payments />)

    expect(container.innerHTML).not.toContain('odd:')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/table.test.tsx`
Ожидается: падение на разрешении `./table`.

- [ ] **Шаг 3: Написать компонент**

```tsx
import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from 'react'

import { cn } from '../lib/cn'

export interface TableProps extends HTMLAttributes<HTMLTableElement> {
  /**
   * Подпись таблицы для скринридера. Обязательна: список без названия
   * читается как набор чисел неизвестно о чём.
   */
  caption: string
  children: ReactNode
}

/**
 * Плотная таблица.
 *
 * Прокрутка живёт на обёртке, а не на странице: иначе широкий столбец с
 * почтой уводит вбок всю разметку вместе с меню.
 */
export function Table({ caption, children, className, ...props }: TableProps) {
  return (
    <div className="overflow-x-auto rounded-md border border-border-subtle">
      <table className={cn('w-full border-collapse text-small', className)} {...props}>
        <caption className="sr-only">{caption}</caption>
        {children}
      </table>
    </div>
  )
}

export function TableHead({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  // Шапка закреплена: в списке на сотню строк заголовки столбцов нужны и внизу.
  return <thead className={cn('sticky top-0 bg-surface-sunken', className)} {...props} />
}

export function TableBody(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...props} />
}

export function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn('border-border-subtle border-b last:border-b-0', className)} {...props} />
}

export function TableHeaderCell({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn('px-3 py-2 text-left font-medium text-text-secondary', className)}
      {...props}
    />
  )
}

export function TableCell({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn('px-3 py-2 text-text', className)} {...props} />
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/table.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, после `Switch`:

```ts
export {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  type TableProps,
  TableRow,
} from './components/table'
```

---

### Задача 6: Tabs

**Файлы:**
- Создать: `frontend/packages/ui/src/components/tabs.tsx`
- Создать: `frontend/packages/ui/src/components/tabs.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт: `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` — обёртки над `@radix-ui/react-tabs` с нашим оформлением. Свойства пробрасываются как есть, поэтому `value`, `defaultValue` и `onValueChange` работают по документации Radix.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Tabs, TabsContent, TabsList, TabsTrigger } from './tabs'

function Periods() {
  return (
    <Tabs defaultValue="today">
      <TabsList aria-label="Период">
        <TabsTrigger value="today">Сегодня</TabsTrigger>
        <TabsTrigger value="week">Неделя</TabsTrigger>
      </TabsList>
      <TabsContent value="today">1 240 ₽</TabsContent>
      <TabsContent value="week">8 700 ₽</TabsContent>
    </Tabs>
  )
}

describe('Tabs', () => {
  it('показывает содержимое выбранной вкладки', () => {
    render(<Periods />)

    expect(screen.getByRole('tab', { name: 'Сегодня', selected: true })).toBeInTheDocument()
    expect(screen.getByText('1 240 ₽')).toBeInTheDocument()
  })

  it('переключается нажатием', async () => {
    render(<Periods />)

    await userEvent.click(screen.getByRole('tab', { name: 'Неделя' }))

    expect(screen.getByText('8 700 ₽')).toBeInTheDocument()
  })

  it('переключается стрелками', async () => {
    /* Ради этого и взят Radix: блуждающий фокус по списку вкладок руками
       пишется долго и почти всегда с ошибкой в краевом случае. */
    render(<Periods />)
    await userEvent.click(screen.getByRole('tab', { name: 'Сегодня' }))

    await userEvent.keyboard('{ArrowRight}')

    expect(screen.getByRole('tab', { name: 'Неделя', selected: true })).toBeInTheDocument()
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/tabs.test.tsx`
Ожидается: падение на разрешении `./tabs`.

- [ ] **Шаг 3: Написать компонент**

```tsx
'use client'

import * as RadixTabs from '@radix-ui/react-tabs'
import type { ComponentPropsWithoutRef } from 'react'

import { cn } from '../lib/cn'

export const Tabs = RadixTabs.Root

export function TabsList({ className, ...props }: ComponentPropsWithoutRef<typeof RadixTabs.List>) {
  return (
    <RadixTabs.List
      className={cn('inline-flex gap-1 rounded-md bg-surface-sunken p-1', className)}
      {...props}
    />
  )
}

export function TabsTrigger({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.Trigger>) {
  return (
    <RadixTabs.Trigger
      className={cn(
        'rounded-sm px-3 py-1.5 text-small text-text-secondary transition-colors',
        'hover:text-text',
        // Выбранная вкладка поднимается на поверхность из утопленной подложки:
        // так видно, что это переключатель, а не набор ссылок.
        'data-[state=active]:bg-surface data-[state=active]:font-medium data-[state=active]:text-text',
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixTabs.Content>) {
  return <RadixTabs.Content className={cn('mt-4', className)} {...props} />
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/tabs.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, после `Table`:

```ts
export { Tabs, TabsContent, TabsList, TabsTrigger } from './components/tabs'
```

---

### Задача 7: DropdownMenu

**Файлы:**
- Создать: `frontend/packages/ui/src/components/dropdown-menu.tsx`
- Создать: `frontend/packages/ui/src/components/dropdown-menu.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт: `DropdownMenu`, `DropdownMenuTrigger`, `DropdownMenuContent`, `DropdownMenuItem`, `DropdownMenuSeparator`.

`DropdownMenuItem` принимает `tone?: 'default' | 'danger'`: опасное действие в списке обязано отличаться от остальных, иначе «Заблокировать» стоит рядом с «Скопировать почту» на одинаковых правах.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './dropdown-menu'

function Actions({ onBan }: { onBan?: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger>Действия</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onSelect={() => undefined}>Заглушить</DropdownMenuItem>
        <DropdownMenuItem tone="danger" onSelect={() => onBan?.()}>
          Заблокировать
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

describe('DropdownMenu', () => {
  it('закрыт до нажатия', () => {
    render(<Actions />)

    expect(screen.queryByRole('menuitem', { name: 'Заглушить' })).toBeNull()
  })

  it('открывается и выполняет выбранное', async () => {
    const onBan = vi.fn()
    render(<Actions onBan={onBan} />)

    await userEvent.click(screen.getByRole('button', { name: 'Действия' }))
    await userEvent.click(screen.getByRole('menuitem', { name: 'Заблокировать' }))

    expect(onBan).toHaveBeenCalledOnce()
  })

  it('опасное действие отличается от остальных', async () => {
    render(<Actions />)
    await userEvent.click(screen.getByRole('button', { name: 'Действия' }))

    expect(screen.getByRole('menuitem', { name: 'Заблокировать' }).className).toContain('danger')
    expect(screen.getByRole('menuitem', { name: 'Заглушить' }).className).not.toContain('danger')
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/dropdown-menu.test.tsx`
Ожидается: падение на разрешении `./dropdown-menu`.

- [ ] **Шаг 3: Написать компонент**

```tsx
'use client'

import * as RadixMenu from '@radix-ui/react-dropdown-menu'
import type { ComponentPropsWithoutRef } from 'react'

import { cn } from '../lib/cn'

export const DropdownMenu = RadixMenu.Root
export const DropdownMenuTrigger = RadixMenu.Trigger

export function DropdownMenuContent({
  className,
  sideOffset = 6,
  ...props
}: ComponentPropsWithoutRef<typeof RadixMenu.Content>) {
  return (
    <RadixMenu.Portal>
      <RadixMenu.Content
        sideOffset={sideOffset}
        className={cn(
          // Меню действительно висит над страницей — здесь тень уместна,
          // в отличие от карточки, которая лежит в потоке.
          'min-w-44 rounded-md border border-border-subtle bg-surface p-1',
          'shadow-[var(--rp-shadow)]',
          className,
        )}
        {...props}
      />
    </RadixMenu.Portal>
  )
}

export interface DropdownMenuItemProps
  extends ComponentPropsWithoutRef<typeof RadixMenu.Item> {
  tone?: 'default' | 'danger' | undefined
}

export function DropdownMenuItem({ className, tone, ...props }: DropdownMenuItemProps) {
  return (
    <RadixMenu.Item
      className={cn(
        'cursor-pointer rounded-sm px-3 py-2 text-small outline-none',
        'data-[highlighted]:bg-surface-sunken',
        tone === 'danger' ? 'text-danger' : 'text-text',
        className,
      )}
      {...props}
    />
  )
}

export function DropdownMenuSeparator({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof RadixMenu.Separator>) {
  return <RadixMenu.Separator className={cn('my-1 h-px bg-border-subtle', className)} {...props} />
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/dropdown-menu.test.tsx`
Ожидается: PASS. Radix в jsdom иногда требует `PointerEvent`; если тест падает на отсутствии этого класса, добавить полифил в `vitest.setup.ts`, а не менять способ нажатия в тесте.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, между `Dialog` и `EmptyState`:

```ts
export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  type DropdownMenuItemProps,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './components/dropdown-menu'
```

---

### Задача 8: Tooltip

**Файлы:**
- Создать: `frontend/packages/ui/src/components/tooltip.tsx`
- Создать: `frontend/packages/ui/src/components/tooltip.test.tsx`
- Изменить: `frontend/packages/ui/src/index.ts`

**Интерфейсы:**
- Отдаёт: `TooltipProvider` и `Tooltip({ label, children })`.

`Tooltip` — не набор частей, а один компонент: у него ровно одно применение — подписать кнопку, у которой осталась одна иконка. Провайдер ставится один раз на приложение.

Подпись дублируется в `aria-label` на обёртке: подсказка Radix появляется по наведению и фокусу, но на телефоне наведения нет вовсе, и без `aria-label` кнопка осталась бы безымянной.

- [ ] **Шаг 1: Написать падающий тест**

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { Tooltip, TooltipProvider } from './tooltip'

describe('Tooltip', () => {
  it('называет кнопку и без наведения', () => {
    /* На телефоне наведения нет. Если подпись живёт только во всплывающем
       окошке, кнопка с одной иконкой остаётся безымянной навсегда. */
    render(
      <TooltipProvider>
        <Tooltip label="Отвязать устройство">
          <button type="button">✕</button>
        </Tooltip>
      </TooltipProvider>,
    )

    expect(screen.getByRole('button', { name: 'Отвязать устройство' })).toBeInTheDocument()
  })
})
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запустить: `pnpm vitest run src/components/tooltip.test.tsx`
Ожидается: падение на разрешении `./tooltip`.

- [ ] **Шаг 3: Написать компонент**

```tsx
'use client'

import * as RadixTooltip from '@radix-ui/react-tooltip'
import type { ReactElement } from 'react'

import { cn } from '../lib/cn'

export const TooltipProvider = RadixTooltip.Provider

export interface TooltipProps {
  label: string
  children: ReactElement
  className?: string | undefined
}

/**
 * Подпись к кнопке, у которой осталась одна иконка.
 *
 * Частей наружу не выставляем: применение ровно одно, и набор из четырёх
 * кусочков здесь означал бы четыре способа собрать одно и то же.
 */
export function Tooltip({ label, children, className }: TooltipProps) {
  return (
    <RadixTooltip.Root>
      <RadixTooltip.Trigger asChild aria-label={label}>
        {children}
      </RadixTooltip.Trigger>
      <RadixTooltip.Portal>
        <RadixTooltip.Content
          sideOffset={6}
          className={cn(
            'rounded-sm bg-text px-2 py-1 text-caption text-bg shadow-[var(--rp-shadow)]',
            className,
          )}
        >
          {label}
        </RadixTooltip.Content>
      </RadixTooltip.Portal>
    </RadixTooltip.Root>
  )
}
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm vitest run src/components/tooltip.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Выставить наружу**

В `src/index.ts`, после `Textarea`:

```ts
export { Tooltip, type TooltipProps, TooltipProvider } from './components/tooltip'
```

- [ ] **Шаг 6: Прогнать пакет целиком**

Запустить: `pnpm vitest run && pnpm typecheck`
Ожидается: PASS обеих команд. Это последняя задача плана — пакет должен быть целым.
