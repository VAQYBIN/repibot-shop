# Админка: каркас, сводка, ноды

> **Для исполнителя:** план выполняется задача за задачей. Шаги помечены `- [ ]`.

**Цель:** дать админке шапку, которой у неё нет вовсе, уплотнить меню и привести сводку и ноды к общему образцу страницы.

**Устройство:** сегодня в админке нельзя ни увидеть, под кем вошёл, ни выйти — кнопки нет ни на одном экране. Шапка появляется в оболочке и потому достаётся всем семи страницам разом. Образец страницы вынесен в `AdminPage` — он уже написан и лежит в `apps/web/src/components/admin-page.tsx`; ваша работа — применить его на сводке и нодах. Пять остальных экранов админки переводит на него соседний план, туда не заходить.

**Стек:** Next.js 16 (App Router), React 19, TanStack Query 5, Tailwind 4, vitest.

## Общие ограничения

- **Ветка `dev`.** Никаких git-команд: коммиты делает ведущий после проверки задачи.
- **Только свои файлы** — те, что в карте ниже. Соседний план в это же время правит `app/admin/{users,tickets,payments,broadcasts}`; другие планы правят `app/account/`, `app/(auth)/`, `apps/miniapp`. Туда не заходить.
- **`components/admin-page.tsx` уже написан.** Его не менять: на него опирается соседний план, и правка разошлась бы с его ожиданиями.
- **Никакого прогона проверок по всему репозиторию.** Только свои тесты: `pnpm --filter @repibot/web test <файл>`.
- **Существующие тесты — договор.** Покрыты `components/admin-shell`, `app/admin/page`, `app/admin/nodes/page`. Обязаны остаться зелёными.
- **Кегли — только по шкале бренда:** `text-display`, `text-h1`, `text-h2`, `text-h3`, `text-body`, `text-small`, `text-caption`. Встроенные погашены и молча не работают.
- **Начертание ставится классом:** `font-semibold` к `text-h1` и `text-h2`, `font-medium` к `text-h3`.
- **Цвета — только токенами.**
- **Админка не переводится.** Подписи остаются русскими строками в коде, как сейчас. Ключей в словари не добавлять.
- **Иконки — через `Icon` из `@repibot/ui`.** Имена сверять по `node_modules/@hugeicons/core-free-icons/dist/index.d.ts`: несуществующее имя даст пустую иконку без ошибки сборки.
- **Комментарии по-русски и о том, почему.** Никаких `// biome-ignore` без сработавшего правила.

## Что уже готово

`AdminPage` из `@/components/admin-page`:

```tsx
export interface AdminPageProps {
  title: string
  description?: string | undefined
  /** Кнопки справа от заголовка: обновить, создать, выгрузить. */
  actions?: ReactNode
  children: ReactNode
}
```

Он сам рисует `<h1 className="text-h1 font-semibold">`, описание под ним и отступы страницы. Страница после перевода на него отдаёт только своё содержимое.

## Карта файлов

| Файл | Что с ним делаем |
|---|---|
| `apps/web/src/components/admin-shell.tsx` | Шапка с выходом, иконки в меню |
| `apps/web/src/components/admin-shell.test.tsx` | Дописать проверки шапки |
| `apps/web/src/app/admin/page.tsx` | Сводка: `AdminPage`, плитки, период на `Tabs` |
| `apps/web/src/app/admin/nodes/page.tsx` | Ноды: `AdminPage`, состояние узла на `Badge` |

---

### Задача 1: Шапка админки

**Файлы:**
- Изменить: `frontend/apps/web/src/components/admin-shell.tsx`
- Изменить: `frontend/apps/web/src/components/admin-shell.test.tsx`

**Интерфейсы:**
- Потребляет: `useMe`, `useLogout` из `@repibot/core`, `ThemeToggle` из `@/components/theme-toggle`, `Icon` и `Button` из `@repibot/ui`.
- Отдаёт: `AdminShell({ children })` — сигнатура не меняется.

Чего сегодня нет: сотрудник не видит, под кем вошёл, и выйти из админки не может. Кнопки выхода нет ни на одной из семи страниц. Переключателя темы тоже нет, а поддержка работает и ночью.

- [ ] **Шаг 1: Написать падающие проверки**

Дописать в `admin-shell.test.tsx` (устройство подмен там уже решено, повторять его не нужно):

```tsx
  it('показывает, под кем вошёл сотрудник', () => {
    render(<AdminShell>содержимое</AdminShell>)

    expect(screen.getByText('staff@example.com')).toBeInTheDocument()
  })

  it('даёт выйти', () => {
    /* До этой правки выйти из админки было нельзя вообще: кнопки не было
       ни на одном из семи экранов. */
    render(<AdminShell>содержимое</AdminShell>)

    expect(screen.getByRole('button', { name: /выйти/i })).toBeInTheDocument()
  })
```

Почта берётся из `useMe`; посмотреть, что именно подставляет существующая подмена в этом файле, и подогнать ожидаемое значение под неё.

- [ ] **Шаг 2: Убедиться, что проверки падают**

Запустить: `pnpm --filter @repibot/web test src/components/admin-shell.test.tsx`
Ожидается: падение двух новых проверок, остальные — зелёные.

- [ ] **Шаг 3: Добавить шапку и иконки**

Меню получает иконки; ссылки, порядок и роли остаются теми же:

```tsx
const LINKS: readonly AdminLink[] = [
  { href: '/admin', label: 'Сводка', roles: ['admin'], icon: ChartLineData01Icon },
  { href: '/admin/users', label: 'Пользователи', roles: ['admin', 'support'], icon: UserGroupIcon },
  { href: '/admin/tickets', label: 'Обращения', roles: ['admin', 'support'], icon: BubbleChatIcon },
  { href: '/admin/payments', label: 'Платежи', roles: ['admin'], icon: CreditCardIcon },
  { href: '/admin/broadcasts', label: 'Рассылки', roles: ['admin'], icon: Mail01Icon },
  { href: '/admin/nodes', label: 'Ноды', roles: ['admin'], icon: ServerStack01Icon },
]
```

Имена значков выше — предположение; проверить каждое и заменить на существующие.

Тип `AdminLink` дополнить полем `icon: IconSvgElement`.

Шапка над всей разметкой, поперёк меню и содержимого:

```tsx
  return (
    <div className="flex min-h-dvh flex-col bg-surface-sunken">
      <header className="flex items-center justify-between gap-4 border-border-subtle border-b bg-surface px-4 py-3">
        <span className="font-medium text-small text-text">{current?.label ?? 'Админка'}</span>
        <div className="flex items-center gap-3">
          {/* Почта, а не имя: в админке важно, под какой учётной записью
              сделано действие, а имя может совпасть у двух сотрудников. */}
          <span className="text-caption text-text-muted">{me.data?.email}</span>
          <ThemeToggle />
          <Button variant="ghost" size="sm" onClick={signOut} disabled={logout.isPending}>
            Выйти
          </Button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* меню — как было, плюс иконка перед подписью */}
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  )
```

`current` — найденная по `pathname` ссылка из `links`. `signOut` написать так же, как он написан в `account-shell.tsx`: `await logout.mutateAsync()`, затем `router.replace('/login')`.

Ссылка в меню получает иконку тем же приёмом, что в кабинете:

```tsx
              <Icon icon={link.icon} size={20} />
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm --filter @repibot/web test src/components/admin-shell.test.tsx`
Ожидается: PASS всех проверок, включая прежние — фильтр ролей и подсветка текущего раздела обязаны работать как раньше.

---

### Задача 2: Сводка

**Файлы:**
- Изменить: `frontend/apps/web/src/app/admin/page.tsx`

**Интерфейсы:**
- Потребляет: `AdminPage`, `Tabs`, `TabsList`, `TabsTrigger`, `Alert`, `Spinner`, `Skeleton`.
- Отдаёт: ничего наружу.

Плитка сводки (строки 56–60) набрана `text-2xl` для числа, `text-sm` для подписи и `text-xs` для пояснения. Число и подпись стоят слишком близко по размеру, чтобы число читалось первым.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Перевести страницу на образец**

Заменить самодельную шапку (строки 118–120) на `AdminPage`:

```tsx
    <AdminPage
      title="Сводка"
      description="Числа по нашей базе. Две плитки — состояние на сейчас, остальные — за выбранный период."
    >
```

Текст описания взять тот, что уже стоит на строке 119, — переписывать его не нужно.

- [ ] **Шаг 3: Уплотнить плитку**

Строки 56–60:

```tsx
      <p className="text-small text-text-secondary">{label}</p>
      {/* Число крупнее подписи вдвое: в сводке первым читается оно. */}
      <p className="mt-2 font-semibold text-h1 text-text">{value}</p>
      <p className="mt-1 text-caption text-text-muted">{caption}</p>
```

- [ ] **Шаг 4: Перевести переключатель периода на вкладки**

Найти, чем сейчас выбирается период (кнопки или список), и заменить на `Tabs`. Значения периодов и обработчик оставить теми же — меняется только вид:

```tsx
        <Tabs value={period} onValueChange={(next) => setPeriod(next as MetricsPeriod)}>
          <TabsList aria-label="Период">
            <TabsTrigger value="today">Сегодня</TabsTrigger>
            <TabsTrigger value="week">Неделя</TabsTrigger>
            <TabsTrigger value="month">Месяц</TabsTrigger>
          </TabsList>
        </Tabs>
```

Подписи и значения свериться по тому, что стоит в файле сейчас: перечисление периодов приходит с сервера, и выдуманное значение даст 422.

`TabsContent` здесь не нужен: содержимое одно, меняются только числа в нём.

- [ ] **Шаг 5: Состояния**

- строка 146: отказ → `<Alert tone="error">`;
- загрузка чисел → шесть `Skeleton` по форме плиток, а не текст: сетка не должна прыгать, когда числа приедут.

- [ ] **Шаг 6: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/page.test.tsx`
Ожидается: PASS. Если тест нажимал на кнопку периода, а теперь это вкладка — падение законно: перевести на `getByRole('tab', { name: … })`.

---

### Задача 3: Ноды

**Файлы:**
- Изменить: `frontend/apps/web/src/app/admin/nodes/page.tsx`

**Интерфейсы:**
- Потребляет: `AdminPage`, `Badge`, `Alert`, `Spinner`.
- Отдаёт: ничего наружу.

Состояние узла сейчас — крашеный текст: `<p className={`text-sm font-medium ${state.className}`}>`. Цвет задаётся строкой класса, собранной в другом месте файла. Это ровно тот случай, ради которого появился `Badge`, и заодно повод убрать сборку классов из данных.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/nodes/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Перевести страницу на образец**

Строки 89–91 заменить на `AdminPage` с тем же заголовком «Ноды» и тем же описанием, что стоит сейчас.

- [ ] **Шаг 3: Заменить состояние бейджем**

Найти, где собирается `state` с полями `label` и `className`, и заменить `className` на `tone: BadgeTone`. Соответствие:

| Состояние узла | Тон |
|---|---|
| подключён и включён | `success` |
| выключен вручную | `neutral` |
| нет связи | `danger` |

Разбор состояний уже написан в файле — менять надо только то, во что он превращается. В разметке (строка 133):

```tsx
                      <Badge tone={state.tone}>{state.label}</Badge>
```

- [ ] **Шаг 4: Состояния и шкала**

- строка 97: «Загружаем узлы…» → `<Spinner label="Загружаем узлы" />`;
- строка 102: отказ → `<Alert tone="error">`;
- строка 116: «Панель не знает ни одного узла» → `EmptyState` с этим же текстом;
- строка 127: заголовок узла `text-lg font-semibold` → `text-h3 font-medium`;
- строки 129, 139, 144: `text-sm` → `text-small`.

- [ ] **Шаг 5: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/nodes/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 6: Проверить всё своё разом**

Запустить: `pnpm --filter @repibot/web test src/components/admin-shell.test.tsx src/app/admin/page.test.tsx src/app/admin/nodes/ && pnpm --filter @repibot/web typecheck`
Ожидается: PASS обеих команд. Это последняя задача плана.
