# Админка: списки, карточка человека, формы

> **Для исполнителя:** план выполняется задача за задачей. Шаги помечены `- [ ]`.

**Цель:** перевести пять рабочих экранов админки на настоящие таблицы, бейджи статусов и общий образец страницы.

**Устройство:** это ежедневные экраны поддержки и владельца — пользователи, карточка человека, обращения, платежи, рассылки. Две таблицы в них свёрстаны вручную, три списка выбора стоят голыми `<select>`, статусы набраны крашеным текстом. Оболочка админки, сводка и ноды переделываются соседним планом и здесь не трогаются.

**Стек:** Next.js 16 (App Router), React 19, TanStack Query 5, Tailwind 4, vitest.

## Общие ограничения

- **Ветка `dev`.** Никаких git-команд: коммиты делает ведущий после проверки задачи.
- **Только свои файлы** — те, что в карте ниже. Соседний план в это же время правит `components/admin-shell.tsx`, `app/admin/page.tsx` и `app/admin/nodes/`; другие планы правят `app/account/`, `app/(auth)/`, `apps/miniapp`. Туда не заходить.
- **`components/admin-page.tsx` уже написан.** Его не менять: на него опирается соседний план.
- **Никакого прогона проверок по всему репозиторию.** Только свои тесты: `pnpm --filter @repibot/web test <файл>`.
- **Существующие тесты — договор.** Покрыты все пять экранов. Обязаны остаться зелёными; упавший тест — повод сначала доказать, что поведение изменилось намеренно.
- **Кегли — только по шкале бренда:** `text-display`, `text-h1`, `text-h2`, `text-h3`, `text-body`, `text-small`, `text-caption`. Встроенные погашены и молча не работают.
- **Начертание ставится классом:** `font-semibold` к `text-h1` и `text-h2`, `font-medium` к `text-h3`.
- **Цвета — только токенами.**
- **Админка не переводится.** Подписи остаются русскими строками в коде. Ключей в словари не добавлять.
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

Он рисует `<h1 className="text-h1 font-semibold">`, описание под ним и отступы страницы. Каждый из пяти экранов переводится на него: самодельная шапка из `<h1>` и абзаца описания убирается, текст переезжает в свойства.

Из `@repibot/ui` доступны `Alert`, `Badge`, `DropdownMenu`, `Select`, `Skeleton`, `Spinner`, `Table`, `Tabs`, `Textarea`, `Tooltip` — вместе со всем, что было раньше.

## Общие замены

Встречаются во всех пяти файлах; отдельно в каждой задаче не повторяю:

| Было | Стало |
|---|---|
| `<p role="alert" className="… text-danger">` | `<Alert tone="error">` |
| `<p role="status">` с сообщением об успехе | `<Alert tone="success">` |
| `<p className="… ">Загрузка…</p>` | `<Spinner label="Загрузка" />` |
| `text-sm` → `text-small`, `text-xs` → `text-caption`, `text-lg` → `text-h3`, `text-2xl` → `text-h1` | по месту |

## Карта файлов

| Файл | Главное изменение |
|---|---|
| `apps/web/src/app/admin/users/page.tsx` | Ручная таблица → `Table` |
| `apps/web/src/app/admin/users/[id]/page.tsx` | Две колонки, действия в `DropdownMenu` |
| `apps/web/src/app/admin/tickets/page.tsx` | `Select` фильтра, статус бейджем, переписка облаками |
| `apps/web/src/app/admin/payments/page.tsx` | `Select` и `Textarea` в формах |
| `apps/web/src/app/admin/broadcasts/page.tsx` | Ручная таблица → `Table`, `Select`, `Textarea` |

---

### Задача 1: Список пользователей

**Файлы:**
- Изменить: `frontend/apps/web/src/app/admin/users/page.tsx`

**Интерфейсы:**
- Потребляет: `AdminPage`, `Table`, `TableBody`, `TableCell`, `TableHead`, `TableHeaderCell`, `TableRow`, `Alert`, `Spinner`, `Skeleton`.
- Отдаёт: ничего наружу.

Таблица на строке 138 свёрстана вручную: `<table className="w-full text-left text-sm">`, шапка отдельным `<tr className="text-text-muted text-xs">`. Она не закреплена при прокрутке и не ездит вбок внутри себя — на узком экране страница уезжает целиком.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/users/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Перевести на образец страницы**

Строки 100–102 (`<h1>` и описание) заменить на `AdminPage` с тем же заголовком «Пользователи» и тем же описанием.

- [ ] **Шаг 3: Заменить таблицу**

`<table aria-label="Пользователи">` со всей его разметкой — на `Table` с тем же составом столбцов. Подпись переезжает из `aria-label` в свойство `caption`: у `Table` она уже размечена как `<caption className="sr-only">`, и второе название сбило бы скринридер.

Ячейки — `TableCell`, заголовки столбцов — `TableHeaderCell`, строки — `TableRow`. Классы вида `text-text-muted text-xs` на шапке убрать: `TableHeaderCell` несёт своё оформление, и вторая копия разойдётся с ним при первой правке.

Номер человека в ячейке (строка 168) остаётся отдельной строкой под именем: `<span className="block text-caption text-text-muted">`.

- [ ] **Шаг 4: Состояния**

- строка 120: «Загрузка…» → пять `Skeleton` строкой по форме таблицы. Форма содержимого здесь известна заранее, и заглушка по ней не заставляет разметку прыгать;
- строка 122: отказ → `<Alert tone="error">`.

- [ ] **Шаг 5: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/users/page.test.tsx`
Ожидается: PASS. Если тест искал таблицу по `aria-label` — падение законно: `getByRole('table', { name: 'Пользователи' })` продолжит работать, потому что `caption` даёт то же имя.

---

### Задача 2: Карточка человека

**Файлы:**
- Изменить: `frontend/apps/web/src/app/admin/users/[id]/page.tsx`

**Интерфейсы:**
- Потребляет: `AdminPage`, `DropdownMenu`, `DropdownMenuContent`, `DropdownMenuItem`, `DropdownMenuSeparator`, `DropdownMenuTrigger`, `Badge`, `Alert`, `Spinner`.
- Отдаёт: ничего наружу.

568 строк и пять разделов одной колонкой: кто он, подписка, действия, дни и тариф, журнал. Сотрудник, открывший карточку, чтобы ответить на вопрос о подписке, листает мимо трёх кнопок блокировки.

**Карточка собирается в две колонки** от `lg`: слева — кто он и подписка, справа — журнал. Действия уезжают в выпадающее меню рядом с именем.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web test "src/app/admin/users/[id]/page.test.tsx"`
Ожидается: PASS.

- [ ] **Шаг 2: Перевести на образец страницы**

Строки 246–252 (хлебная крошка, `<h1>` с именем, номер) — на `AdminPage`, где `title` — имя человека, `description` — его номер. Хлебную крошку оставить над ним, она не часть образца.

- [ ] **Шаг 3: Собрать действия в меню**

Раздел «Действия» (строки 382–434) перестаёт быть карточкой с рядом кнопок и становится меню в свойстве `actions` у `AdminPage`:

```tsx
      actions={
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" disabled={busy}>
              Действия
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onSelect={() => moderate.mutate(row.support_muted ? 'unmute' : 'mute')}
            >
              {row.support_muted ? 'Открыть поддержку' : 'Закрыть поддержку'}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => setConfirmation('revoke')}>
              Выпустить новую ссылку
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {row.banned ? (
              <DropdownMenuItem onSelect={() => moderate.mutate('unblock')}>
                Разблокировать
              </DropdownMenuItem>
            ) : (
              /* Блокировка отделена чертой и покрашена как опасная: человек по
                 ту сторону теряет и покупки, и разговор, и узнаёт об этом сам.
                 Подтверждение диалогом при этом остаётся — меню его не заменяет. */
              <DropdownMenuItem tone="danger" onSelect={() => setConfirmation('block')}>
                Заблокировать
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      }
```

Сообщения `notice` и `actionError` (строки 388–397) из удалённого раздела переезжают наверх страницы, сразу под `AdminPage`: `<Alert tone="success">` и `<Alert tone="error">`. Терять их нельзя — это единственный ответ на нажатие.

Раздел «Дни и тариф» (со строки 436) остаётся карточкой: это форма, а не действие в один щелчок, и в меню ей не место.

- [ ] **Шаг 4: Разложить в две колонки**

Разделы «кто он» и «подписка» — в левую колонку, «журнал» — в правую:

```tsx
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)] lg:items-start">
        <div className="flex flex-col gap-6">
          {/* кто он, подписка, дни и тариф */}
        </div>
        <div>{/* журнал */}</div>
      </div>
```

Ниже `lg` колонки складываются одна под другую в том же порядке — журнал внизу, как сейчас.

- [ ] **Шаг 5: Статусы и шкала**

- заголовки разделов (строки 257, 299, 384 и далее) → `text-h3 font-medium text-text`;
- статус подписки в разделе «подписка» — `Badge` с тем же соответствием тонов, что в кабинете: `active` → `success`, `trial` → `info`, `pending_provision` → `warning`, `expired` и `disabled` → `danger`, прочее → `neutral`;
- признак блокировки рядом с именем — `<Badge tone="danger">Заблокирован</Badge>`, если `row.banned`;
- строки 228, 322: «Загрузка…» → `<Spinner label="Загрузка" />`;
- строки 233, 327: отказы → `<Alert tone="error">`;
- оставшиеся `text-xs` → `text-caption`, `text-sm` → `text-small`, `text-lg` → `text-h3`, `text-base` → `text-body`.

- [ ] **Шаг 6: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web test "src/app/admin/users/[id]/page.test.tsx"`
Ожидается: PASS. Тест почти наверняка нажимал кнопки действий напрямую — теперь до них надо сначала открыть меню. Это законное падение: дописать открытие меню перед нажатием, `getByRole('menuitem', …)` вместо `getByRole('button', …)`. Проверка того, что действие вызвано, обязана остаться прежней.

---

### Задача 3: Обращения

**Файлы:**
- Изменить: `frontend/apps/web/src/app/admin/tickets/page.tsx`

**Интерфейсы:**
- Потребляет: `AdminPage`, `Select`, `Badge`, `Alert`, `Spinner`.
- Отдаёт: ничего наружу.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/tickets/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Перевести на образец и заменить фильтр**

Строки 139–141 → `AdminPage` с тем же заголовком и описанием.

Строка 154: `<select>` со своими классами → `<Select>` с теми же `id`, `value`, `onChange` и теми же `<option>`. Классы убрать целиком.

- [ ] **Шаг 3: Статус обращения бейджем**

В списке обращений статус сейчас — часть подписи. Вынести его в `Badge` рядом с темой:

| Статус обращения | Тон |
|---|---|
| ждёт ответа персонала | `danger` |
| ждёт ответа человека | `warning` |
| закрыто | `success` |

Соответствие повторяет эмодзи в названиях тем супергруппы: красное — то, что ждёт нас; жёлтое — то, что ждёт человека; зелёное — решённое. Один и тот же смысл в двух местах обязан выглядеть одинаково.

Названия статусов и их значения взять из файла — они уже разобраны выше по коду.

- [ ] **Шаг 4: Развести своё и чужое в переписке**

Сообщения в ленте (около строки 231) прижимаются к разным краям: ответ персонала — вправо, на подложке `bg-jade-mist`; сообщение человека — влево, на `bg-surface` с границей. Подпись автора остаётся.

```tsx
                  <li className={staff ? 'flex justify-end' : 'flex justify-start'}>
                    <div
                      className={cn(
                        'max-w-[85%] rounded-md border px-4 py-3',
                        staff ? 'border-transparent bg-jade-mist' : 'border-border-subtle bg-surface',
                      )}
                    >
```

`staff` вычисляется по автору сообщения — как именно, видно из разбора авторов в этом же файле. `cn` берётся из `@repibot/ui`.

- [ ] **Шаг 5: Состояния и шкала**

- строки 168, 213: «Загрузка…» → `<Spinner label="Загрузка" />`;
- строки 170, 215: отказы → `<Alert tone="error">`;
- заголовки разделов (148, 206) → `text-h3 font-medium text-text`;
- оставшиеся `text-sm` → `text-small`, `text-xs` → `text-caption`.

- [ ] **Шаг 6: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/tickets/page.test.tsx`
Ожидается: PASS.

---

### Задача 4: Платежи

**Файлы:**
- Изменить: `frontend/apps/web/src/app/admin/payments/page.tsx`

**Интерфейсы:**
- Потребляет: `AdminPage`, `Select`, `Textarea`, `Alert`, `FormField`.
- Отдаёт: ничего наружу.

Экран из двух форм — возврат и компенсация. Обе размечены руками: `<label>` отдельно, поле отдельно, ошибка отдельным абзацем. `FormField` в пакете умеет связывать всё это сам, включая `aria-describedby` и `aria-invalid`.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/payments/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Перевести на образец**

Строки 67–69 → `AdminPage` с тем же заголовком «Платежи и корректировки» и описанием.

- [ ] **Шаг 3: Заменить поля**

- строка 150: `<select>` действия компенсации → `<Select>` с теми же значениями;
- поля комментариев (строки 110, 163) — если это `<input>`, оставить `Input`; если многострочные — `Textarea`;
- пары «подпись плюс поле» (строки 75, 99, 110, 147, 163) обернуть в `FormField` с `label` и `htmlFor`, совпадающим с `id` поля. Отдельные `<label className="text-sm font-medium">` при этом убираются: `FormField` рисует подпись сам.

- [ ] **Шаг 4: Состояния и шкала**

- строки 122, 175: отказы → `<Alert tone="error">` внутри `FormField` через свойство `error`, если ошибка относится к полю, и отдельным `Alert` — если ко всей форме;
- заголовки разделов (91, 138) → `text-h3 font-medium text-text`;
- оставшиеся `text-sm` → `text-small`.

- [ ] **Шаг 5: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/payments/page.test.tsx`
Ожидается: PASS. Подписи полей остаются теми же строками, поэтому поиск по `getByLabelText` продолжит работать.

---

### Задача 5: Рассылки

**Файлы:**
- Изменить: `frontend/apps/web/src/app/admin/broadcasts/page.tsx`

**Интерфейсы:**
- Потребляет: `AdminPage`, `Table` и его части, `Select`, `Textarea`, `Badge`, `Alert`, `FormField`.
- Отдаёт: ничего наружу.

433 строки: таблица кампаний и форма создания. Таблица (строка 199) свёрстана вручную и даже без `aria-label` — скринридер читает её как набор чисел неизвестно о чём.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/broadcasts/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Перевести на образец**

Строки 176–178 → `AdminPage` с тем же заголовком «Рассылки» и описанием.

- [ ] **Шаг 3: Заменить таблицу кампаний**

`<table className="w-full text-left text-sm">` со всей разметкой — на `Table` с `caption="Кампании"`. Состав столбцов не меняется. Статус кампании выносится в `Badge`:

| Состояние кампании | Тон |
|---|---|
| черновик | `neutral` |
| идёт | `info` |
| приостановлена | `warning` |
| завершена | `success` |
| отменена | `danger` |

Названия состояний взять из файла — разбор уже написан.

- [ ] **Шаг 4: Заменить поля формы**

- строка 280: `<select>` сегмента → `<Select>`;
- строка 305 и соседние: подписи и поля обернуть в `FormField`;
- многострочные поля текстов кампании → `Textarea`.

Тексты кампании набираются на двух языках. Если поля стоят парой без разделения, оставить как есть: это устройство формы, а не оформление, и менять его этот план не должен.

- [ ] **Шаг 5: Состояния и шкала**

- строки 189, 259: отказы → `<Alert tone="error">`;
- строка 194: «Загрузка…» → `<Spinner label="Загрузка" />`;
- заголовки разделов (185, 268) → `text-h3 font-medium text-text`;
- оставшиеся `text-sm` → `text-small`, `text-xs` → `text-caption`.

- [ ] **Шаг 6: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web test src/app/admin/broadcasts/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 7: Проверить всё своё разом**

Запустить: `pnpm --filter @repibot/web test src/app/admin/users/ src/app/admin/tickets/ src/app/admin/payments/ src/app/admin/broadcasts/ && pnpm --filter @repibot/web typecheck`
Ожидается: PASS обеих команд. Это последняя задача плана.
