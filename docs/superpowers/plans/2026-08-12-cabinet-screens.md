# Кабинет: остальные пять экранов

> **Для исполнителя:** план выполняется задача за задачей. Шаги помечены `- [ ]`.

**Цель:** привести профиль, уведомления, платежи, безопасность и поддержку к тому же виду, что и якорный экран подписки.

**Устройство:** образец страницы уже задан якорным экраном и повторяется здесь без изменений: `<main className="flex flex-col gap-6">`, заголовок `text-h1 font-semibold text-text`, дальше карточки разделов с заголовками `text-h3 font-medium`. Ни оболочка, ни экран подписки в этом плане не трогаются — они уже сделаны.

**Стек:** Next.js 16 (App Router), React 19, TanStack Query 5, Tailwind 4, vitest.

## Общие ограничения

- **Ветка `dev`.** Никаких git-команд: коммиты делает ведущий после проверки задачи.
- **Только свои пять файлов** — те, что перечислены в карте ниже. Весь `apps/web/src/components/` в этом плане чужой: `account-shell`, `subscription-card`, `traffic-bar`, `device-list` правит план якорного экрана, `plan-card` — план входа и публичных страниц. Туда не заходить даже ради однострочной правки. Чужие также `app/(auth)`, `app/admin`, `app/account/subscription/` и весь `apps/miniapp`.
- **Никакого прогона проверок по всему репозиторию.** Только свои тесты: `pnpm --filter @repibot/web vitest run <файл>`.
- **Существующие тесты — договор.** Четыре из пяти экранов покрыты: `notifications`, `payments`, `security`, `support`. Они обязаны остаться зелёными. Упавший тест — повод сначала доказать, что поведение изменилось намеренно.
- **Кегли — только по шкале бренда:** `text-display`, `text-h1`, `text-h2`, `text-h3`, `text-body`, `text-small`, `text-caption`. Встроенные `text-sm`, `text-lg`, `text-xl`, `text-2xl`, `text-xs`, `text-base` погашены и молча не работают.
- **Начертание ставится классом:** `font-semibold` к `text-h1`, `font-medium` к `text-h3`.
- **Цвета — только токенами.**
- **Иконки — через `Icon` из `@repibot/ui`.** Имена сверять по `node_modules/@hugeicons/core-free-icons/dist/index.d.ts`.
- **Новых ключей словаря не заводить.** Всё, что нужно, уже переведено.
- **Комментарии по-русски и о том, почему.** Никаких `// biome-ignore` без сработавшего правила.

## Общие замены

Одни и те же три замены встречаются во всех пяти файлах. Делать их везде, отдельно в каждой задаче не повторяю:

| Было | Стало |
|---|---|
| `<p role="alert" className="... text-danger">` | `<Alert tone="error">…</Alert>` |
| `<p role="status">{t('common.loading')}</p>` | `<Spinner label={t('common.loading')} />` |
| `text-sm` → `text-small`, `text-xs` → `text-caption`, `text-lg` → `text-h3`, `text-2xl` → `text-h1` | по месту |

`Alert` сам выбирает роль по тону: `error` объявляет немедленно, остальные ждут очереди. Поэтому `role` руками больше нигде не пишется.

---

### Задача 1: Профиль

**Файлы:**
- Изменить: `frontend/apps/web/src/app/account/page.tsx`

**Интерфейсы:**
- Потребляет: `Select`, `Alert`, `Spinner` из `@repibot/ui`.
- Отдаёт: ничего наружу.

Экран не покрыт тестами. Он же — единственный, где список языка свёрстан голым `<select>` с классами, скопированными из `Input`: ровно тот случай, ради которого `Select` и появился.

- [ ] **Шаг 1: Заменить список языка**

Строки 54–65: убрать `<select>` со своими классами и поставить компонент. Классы удалить целиком — `Select` несёт их сам, и оставленная копия разойдётся с оригиналом при первой же правке поля:

```tsx
            <Select
              id="language"
              value={chosen}
              onChange={(event) => setChosen(event.target.value as Language)}
            >
              {LANGUAGES.map((code) => (
                <option key={code} value={code}>
                  {code === 'ru' ? 'Русский' : 'English'}
                </option>
              ))}
            </Select>
```

- [ ] **Шаг 2: Привести состояния и шкалу**

- строка 28: загрузка → `<Spinner label={t('common.loading')} />`;
- строка 29: `<p role="alert">` → `<Alert tone="error">{t('common.error')}</Alert>`;
- строка 39: заголовок → `text-h1 font-semibold text-text`;
- строка 69: отказ сохранения → `<Alert tone="error">`;
- строки 79, 86: `text-sm` → `text-small`;
- обёртка `main` — `flex flex-col gap-6`.

- [ ] **Шаг 3: Написать тест на список языка**

Создать `frontend/apps/web/src/app/account/page.test.tsx`. Устройство подмен взять из соседнего `notifications/page.test.tsx` — там уже решено, как подставлять запросы и язык.

```tsx
it('язык выбирается нативным списком', async () => {
  render(<AccountPage />)

  const select = screen.getByRole('combobox', { name: /язык|language/i })
  await userEvent.selectOptions(select, 'en')

  expect(select).toHaveValue('en')
})
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/page.test.tsx`
Ожидается: PASS.

---

### Задача 2: Уведомления

**Файлы:**
- Изменить: `frontend/apps/web/src/app/account/notifications/page.tsx`

**Интерфейсы:**
- Потребляет: `Alert`, `Spinner`.
- Отдаёт: ничего наружу.

Экран короткий — 53 строки, — и правки в нём только по общей таблице замен. Отдельная мелочь: пояснение к служебным уведомлениям (строка 41) набрано `text-text-muted` и стоит вплотную к переключателям. Разнести его в отдельный абзац через `mt-4` с `text-caption` — это подпись, а не текст наравне с остальным.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/notifications/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Применить замены**

- строка 20: заголовок → `text-h1 font-semibold text-text`;
- строка 24: загрузка → `<Spinner label={t('common.loading')} />`;
- строки 26 и 46: отказы → `<Alert tone="error">`;
- строка 38: `text-sm` → `text-small`;
- строка 41: `text-sm text-text-muted` → `text-caption text-text-muted`;
- обёртка `main` — `flex flex-col gap-6`.

- [ ] **Шаг 3: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/notifications/page.test.tsx`
Ожидается: PASS.

---

### Задача 3: Платежи

**Файлы:**
- Изменить: `frontend/apps/web/src/app/account/payments/page.tsx`

**Интерфейсы:**
- Потребляет: `Alert`, `Spinner`, `Skeleton`, `Table`, `TableBody`, `TableCell`, `TableHead`, `TableHeaderCell`, `TableRow`, `Badge`.
- Отдаёт: ничего наружу.

Самый большой экран кабинета — 435 строк. Замен по общей таблице в нём около тридцати; кроме них — одна настоящая переделка: список заказов.

**Список заказов становится таблицей от `md`.** Сегодня каждый заказ — отдельная `Card` с названием слева и статусом справа. Десяток таких карточек подряд читается хуже, чем десять строк таблицы: глазу негде вести линию. На узком экране таблица не годится, поэтому карточки остаются — но только там.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/payments/page.test.tsx`
Ожидается: PASS. Запомнить число проверок — после правки оно обязано совпасть.

- [ ] **Шаг 2: Применить общие замены**

Пройти по файлу и заменить, ничего не пропуская:

- заголовок страницы (строка 126) → `text-h1 font-semibold text-text`;
- заголовки разделов (строки 162, 229, 272, 337, 382) → `text-h3 font-medium text-text`;
- заголовок тарифа в карточке (строка 171) → `text-h3 font-medium text-text`;
- все `role="alert"` (строки 151, 216, 244, 253, 278, 326, 331, 342, 363, 391) → `<Alert tone="error">`;
- все загрузки с `common.loading` (строки 146, 211, 249, 274, 287, 386) → `<Spinner label={t('common.loading')} />`;
- `role="status"` с сообщением об успехе (строки 140, 222) → `<Alert tone="success">`;
- оставшиеся `text-sm` → `text-small`.

- [ ] **Шаг 3: Переделать список заказов**

Заменить блок со строки 400 (`) : (` перед `<ul className="mt-3 space-y-2">`) по строку 421 включительно:

```tsx
        ) : (
          <>
            {/* Ниже md таблица не помещается: восемь столбцов на четырёх
                дюймах превращаются в горизонтальную прокрутку каждой строки. */}
            <ul className="mt-3 space-y-2 md:hidden">
              {orders.data?.map((order) => (
                <li key={order.id}>
                  <Card>
                    <div className="flex justify-between gap-3">
                      <span className="font-medium text-text">
                        {localized(order.plan_name, language, order.plan_code)}
                      </span>
                      <span className="text-small text-text-secondary">{orderStatus(order, t)}</span>
                    </div>
                    <time
                      className="mt-1 block text-small text-text-secondary"
                      dateTime={order.expires_at}
                    >
                      {formatDate(order.expires_at, language)}
                    </time>
                  </Card>
                </li>
              ))}
            </ul>

            <div className="mt-3 hidden md:block">
              <Table caption={t('payment.orders')}>
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>{t('plans.title')}</TableHeaderCell>
                    <TableHeaderCell>{t('subscription.expires_at')}</TableHeaderCell>
                    <TableHeaderCell>{t('payment.status')}</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {orders.data?.map((order) => (
                    <TableRow key={order.id}>
                      <TableCell className="font-medium">
                        {localized(order.plan_name, language, order.plan_code)}
                      </TableCell>
                      <TableCell className="tabular-nums text-text-secondary">
                        <time dateTime={order.expires_at}>
                          {formatDate(order.expires_at, language)}
                        </time>
                      </TableCell>
                      <TableCell>{orderStatus(order, t)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </>
        )}
```

Ключ `payment.status` может не существовать в словаре. Проверить по `frontend/packages/core/src/i18n/ru.ts`; если его нет — взять существующий ключ, подходящий по смыслу, а новый не заводить: этот план словарей не трогает.

Заказ существует в двух представлениях одновременно, поэтому оба содержат одинаковый текст — тест, ищущий название тарифа, найдёт его дважды. Если существующий тест на этом упал, он упал законно: перевести его на `getAllByText` с проверкой длины.

- [ ] **Шаг 4: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/payments/page.test.tsx`
Ожидается: PASS. Число проверок то же, что до правки.

---

### Задача 4: Безопасность

**Файлы:**
- Изменить: `frontend/apps/web/src/app/account/security/page.tsx`

**Интерфейсы:**
- Потребляет: `Alert`, `Spinner`, `Skeleton`.
- Отдаёт: ничего наружу.

420 строк и пять разделов подряд: пароль, почта, ключи доступа, сессии, Telegram. Все пять набраны одинаково и стоят одной стопкой, поэтому опасное соседствует с обычным на равных правах.

**Разделы группируются по смыслу**, порядок меняется:

1. **Способы входа** — пароль, почта, ключи доступа, Telegram.
2. **Сессии** — где человек вошёл сейчас.

Группа получает заголовок `text-h2 font-semibold` и разделительную линию сверху; карточки внутри остаются как есть. Группировка — единственная перестановка; ни одно действие не исчезает и ни одно не появляется.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/security/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Применить общие замены**

- строка 107: заголовок страницы → `text-h1 font-semibold text-text`;
- строки 110, 165, 206, 264, 305: заголовки карточек → `text-h3 font-medium text-text`;
- строки 142, 185, 210, 266, 315, 357: отказы → `<Alert tone="error">`;
- строки 162, 216, 271: загрузки → `<Spinner label={t('common.loading')} />`;
- строки 152, 195: сообщения об успехе → `<Alert tone="success">`;
- строка 343: код привязки `font-mono text-2xl` → `font-mono text-h1`;
- оставшиеся `text-sm` → `text-small`.

- [ ] **Шаг 3: Сгруппировать разделы**

Обернуть карточки в две группы. Заголовки взять из существующих ключей словаря; если подходящего ключа для названия группы нет — использовать заголовок первой карточки группы как заголовок группы и не заводить новых ключей:

```tsx
      <section className="flex flex-col gap-4">
        <h2 className="text-h2 font-semibold text-text">{t('account.login_methods')}</h2>
        {/* пароль, почта, ключи доступа, Telegram — карточки без изменений */}
      </section>

      <section className="flex flex-col gap-4 border-t border-border-subtle pt-6">
        <h2 className="text-h2 font-semibold text-text">{t('account.sessions')}</h2>
        {/* карточка сессий; её собственный заголовок при этом убирается —
            иначе одно и то же название стоит дважды подряд */}
      </section>
```

Проверить наличие ключа `account.login_methods` по `frontend/packages/core/src/i18n/ru.ts`. Если его нет — взять `account.security` для первой группы, а `account.sessions` для второй; новых ключей не заводить.

- [ ] **Шаг 4: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/security/page.test.tsx`
Ожидается: PASS. Если тест искал заголовок «Сессии» и теперь находит его дважды — падение законно, перевести проверку на `getAllByRole('heading', …)`. Если упало что-то другое — виновата правка.

---

### Задача 5: Поддержка

**Файлы:**
- Изменить: `frontend/apps/web/src/app/account/support/page.tsx`

**Интерфейсы:**
- Потребляет: `Alert`, `Spinner`, `Textarea`, `Badge`.
- Отдаёт: ничего наружу.

Два голых `<textarea>` со скопированными классами (строки 100 и 224) заменяются компонентом. И одна настоящая переделка: **свои сообщения в переписке отличаются от чужих формой, а не только подписью.**

Сегодня каждое сообщение — одинаковая `Card` с автором сверху. Кто написал, видно только прочитав подпись; лента из десяти таких карточек читается как протокол, а не как разговор.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/support/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Заменить поля ввода**

Строки 100 и 224: убрать `<textarea>` вместе с его классами и поставить `<Textarea>` с теми же `id`, `rows`, `placeholder`, `value`, `onChange`. Классы удалить целиком: оставленная копия разойдётся с оригиналом при первой правке поля.

- [ ] **Шаг 3: Применить общие замены**

- строка 83: заголовок → `text-h1 font-semibold text-text`;
- строки 96, 121, 169: заголовки разделов → `text-h3 font-medium text-text`;
- строки 113, 130, 190, 238, 243: отказы → `<Alert tone="error">`;
- строки 125, 185: загрузки → `<Spinner label={t('common.loading')} />`;
- строка 89: `role="status"` с состоянием → `<Alert tone="info">`;
- строка 218: сообщение о закрытом обращении → `<Alert tone="info">`;
- оставшиеся `text-sm` → `text-small`.

- [ ] **Шаг 4: Развести своё и чужое в переписке**

Заменить содержимое `<li>` в ленте сообщений (строки 200–213). Определить, какое значение `message.author` означает самого человека, посмотрев в `AUTHOR` в этом же файле:

```tsx
                <li key={message.id} className={mine ? 'flex justify-end' : 'flex justify-start'}>
                  {/* Своё прижато вправо и залито акцентной подложкой, чужое
                      лежит слева на поверхности. Подпись остаётся, но теперь
                      она подтверждает то, что и так видно, а не сообщает. */}
                  <div
                    className={cn(
                      'max-w-[85%] rounded-md border px-4 py-3',
                      mine
                        ? 'border-transparent bg-jade-mist'
                        : 'border-border-subtle bg-surface',
                    )}
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-small font-medium text-text">
                        {label(AUTHOR, message.author, t)}
                      </span>
                      <time className="text-caption text-text-secondary" dateTime={message.created_at}>
                        {formatDate(message.created_at, language)}
                      </time>
                    </div>
                    {/* Сообщение остаётся текстом: разметку в нём не разбираем. */}
                    <p className="mt-1 whitespace-pre-wrap text-text">{message.body}</p>
                  </div>
                </li>
```

`mine` вычисляется прямо в `map`. Проверка идёт по автору сообщения, а не по его номеру: номер человека на этом экране не известен.

`cn` берётся из `@repibot/ui`. Список остаётся `<ul>` — это по-прежнему перечень, и скринридер обязан считать его перечнем.

Класс `space-y-2` на списке заменить на `space-y-3`: соседние облака сообщений нуждаются в большем зазоре, чем одинаковые карточки.

- [ ] **Шаг 5: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/support/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 6: Прогнать весь кабинет и типы**

Запустить: `pnpm --filter @repibot/web vitest run src/app/account/ && pnpm --filter @repibot/web typecheck`
Ожидается: PASS обеих команд. Это последняя задача плана.
