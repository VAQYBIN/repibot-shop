# Вход и публичные страницы

> **Для исполнителя:** план выполняется задача за задачей. Шаги помечены `- [ ]`.

**Цель:** привести шесть экранов входа к одному образцу, развести на них разные способы входа, и перевести четыре публичные страницы на шкалу и колонку чтения.

**Устройство:** экраны входа сегодня набраны каждый по-своему и сообщают об отказе своим абзацем. Общий образец задаётся в `(auth)/layout.tsx` — он один на все шесть, — а сами страницы теряют самодельную обвязку. Публичные страницы получают колонку чтения `max-w-2xl` и шкалу, больше ничего.

**Стек:** Next.js 16 (App Router), React 19, Tailwind 4, vitest.

## Общие ограничения

- **Ветка `dev`.** Никаких git-команд: коммиты делает ведущий после проверки задачи.
- **Только свои файлы** — те, что перечислены в карте ниже. Соседние планы в это же время правят `app/account/`, `app/admin/`, `components/account-shell.tsx`, `components/subscription-card.tsx`, `components/traffic-bar.tsx`, `components/device-list.tsx` и весь `apps/miniapp`. Туда не заходить.
- **Никакого прогона проверок по всему репозиторию.** Только свои тесты: `pnpm --filter @repibot/web test <файл>`.
- **Существующие тесты — договор.** Покрыты `(auth)/login`, `(auth)/confirm-email`, `plans`, `winback`, `components/plan-card`. Обязаны остаться зелёными.
- **Кегли — только по шкале бренда:** `text-display`, `text-h1`, `text-h2`, `text-h3`, `text-body`, `text-small`, `text-caption`. Встроенные погашены и молча не работают.
- **Начертание ставится классом:** `font-semibold` к `text-h1` и `text-h2`, `font-medium` к `text-h3`.
- **Цвета — только токенами.**
- **Юридические тексты не трогать ни словом.** Страница документа — заглушка, и она остаётся заглушкой: содержимое из таблицы `legal_documents` этот подпроект не подключает.
- **Новых ключей словаря не заводить.**
- **Комментарии по-русски и о том, почему.** Никаких `// biome-ignore` без сработавшего правила.

## Карта файлов

| Файл | Что с ним делаем |
|---|---|
| `apps/web/src/app/layout.tsx` | Провайдер подсказок Radix на всё приложение |
| `apps/web/src/app/(auth)/layout.tsx` | Знак сверху, колонка формы, общий образец |
| `apps/web/src/app/(auth)/login/page.tsx` | Способы входа разводятся на два блока |
| `apps/web/src/app/(auth)/register/page.tsx` | Отказы через `Alert`, шкала |
| `apps/web/src/app/(auth)/forgot-password/page.tsx` | То же |
| `apps/web/src/app/(auth)/reset-password/page.tsx` | То же |
| `apps/web/src/app/(auth)/verify-email/page.tsx` | То же |
| `apps/web/src/app/(auth)/confirm-email/page.tsx` | То же |
| `apps/web/src/app/plans/page.tsx` | Состояния на `Spinner` и `Alert` |
| `apps/web/src/components/plan-card.tsx` | Самодельная плашка → `Badge`, шкала |
| `apps/web/src/app/legal/[slug]/page.tsx` | Колонка чтения и шкала |
| `apps/web/src/app/unsubscribe/page.tsx` | Шкала, отказ через `Alert` |
| `apps/web/src/app/winback/page.tsx` | Шкала, состояния |

---

### Задача 1: Провайдер подсказок

**Файлы:**
- Изменить: `frontend/apps/web/src/app/layout.tsx`

**Интерфейсы:**
- Потребляет: `TooltipProvider` из `@repibot/ui`.
- Отдаёт: возможность применять `Tooltip` где угодно в вебе. Без этого провайдера подсказка не работает нигде — соседний план админки на неё рассчитывает.

- [ ] **Шаг 1: Обернуть приложение**

В `RootLayout` добавить провайдер внутрь `AuthProvider`:

```tsx
        <BrowserPreferencesProvider>
          <AuthProvider>
            {/* Подсказкам Radix нужен один общий провайдер на приложение:
                он держит задержку появления и следит, чтобы две подсказки
                не всплыли разом. */}
            <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
          </AuthProvider>
        </BrowserPreferencesProvider>
```

`TooltipProvider` — клиентский компонент, а `layout.tsx` серверный. Если сборка на это ругается, обернуть провайдер в собственный клиентский компонент `apps/web/src/components/tooltip-provider.tsx` с `'use client'` наверху, а не переводить весь layout в клиентские.

- [ ] **Шаг 2: Убедиться, что приложение собирается**

Запустить: `pnpm --filter @repibot/web typecheck`
Ожидается: PASS.

---

### Задача 2: Общий образец входа

**Файлы:**
- Изменить: `frontend/apps/web/src/app/(auth)/layout.tsx`

**Интерфейсы:**
- Потребляет: `Lockup` из `@/components/lockup`.
- Отдаёт: обёртку всех шести экранов входа. Страницы после этого отдают только форму и заголовок — знак и центрирование берёт на себя оболочка.

Сегодня оболочка — тринадцать строк с колонкой `max-w-md` и ничем больше. Человек, попавший на форму входа по ссылке из письма, не видит, куда попал: знака на странице нет.

- [ ] **Шаг 1: Переписать оболочку**

```tsx
import type { ReactNode } from 'react'

import { Lockup } from '@/components/lockup'

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-8 p-6">
      {/* Знак на всех шести экранах: человек попадает сюда по ссылке из
          письма и должен видеть, куда именно он попал. */}
      <Lockup size={32} />
      {children}
    </main>
  )
}
```

Колонка сужается с `max-w-md` (28rem) до `max-w-sm` (24rem): форма из двух полей на 28rem растягивается настолько, что подпись и поле перестают читаться как пара.

- [ ] **Шаг 2: Убедиться, что вход по-прежнему работает**

Запустить: `pnpm --filter @repibot/web test "src/app/(auth)/"`
Ожидается: PASS. Тесты страниц не знают об оболочке и упасть не должны.

---

### Задача 3: Экран входа

**Файлы:**
- Изменить: `frontend/apps/web/src/app/(auth)/login/page.tsx`

**Интерфейсы:**
- Потребляет: `Alert` из `@repibot/ui`.
- Отдаёт: образец разведения способов входа, который повторяет экран регистрации.

Сегодня на экране четыре кнопки подряд: «Войти», ссылки, «Ключ доступа», «Telegram». Все набраны одинаково, и человек читает их как четыре шага одного пути, хотя это три разных пути к одному и тому же.

- [ ] **Шаг 1: Убедиться, что тест сейчас зелёный**

Запустить: `pnpm --filter @repibot/web test "src/app/(auth)/login/page.test.tsx"`
Ожидается: PASS.

- [ ] **Шаг 2: Развести способы входа**

Заголовок (строка 69) → `text-h1 font-semibold text-text`.

Оба отказа (строки 71–75 и 98–102) → `<Alert tone="error">`.

Строку ссылок (строка 108) → `className="flex justify-between text-small"`.

После кнопки «Войти» и строки ссылок — разделитель, и только под ним остальные способы:

```tsx
      {/* Разделитель отделяет вход по паролю от остальных способов: без него
          четыре кнопки подряд читаются как четыре шага одного пути. */}
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-border-subtle" />
        <span className="text-caption text-text-muted">
          {language === 'ru' ? 'или' : 'or'}
        </span>
        <span className="h-px flex-1 bg-border-subtle" />
      </div>

      <div className="flex flex-col gap-3">
        {/* кнопка ключа доступа и кнопка Telegram — как были */}
      </div>
```

Разделитель помечен `aria-hidden`: слово «или» между кнопками нужно глазу, а скринридеру оно ничего не добавляет — кнопки он и так перечисляет по одной.

Переменная `language` в этом файле уже есть; если её нет под этим именем, взять то, что использует `useTranslate` выше по файлу.

- [ ] **Шаг 3: Убедиться, что тест по-прежнему зелёный**

Запустить: `pnpm --filter @repibot/web test "src/app/(auth)/login/page.test.tsx"`
Ожидается: PASS.

---

### Задача 4: Остальные пять экранов входа

**Файлы:**
- Изменить: `frontend/apps/web/src/app/(auth)/register/page.tsx`
- Изменить: `frontend/apps/web/src/app/(auth)/forgot-password/page.tsx`
- Изменить: `frontend/apps/web/src/app/(auth)/reset-password/page.tsx`
- Изменить: `frontend/apps/web/src/app/(auth)/verify-email/page.tsx`
- Изменить: `frontend/apps/web/src/app/(auth)/confirm-email/page.tsx`

**Интерфейсы:**
- Потребляет: `Alert`, `Spinner`.
- Отдаёт: ничего наружу.

- [ ] **Шаг 1: Пройти по каждому файлу**

В каждом из пяти:

- заголовок `text-2xl font-semibold` → `text-h1 font-semibold`;
- каждый `<p role="alert" className="… text-danger">` → `<Alert tone="error">`;
- каждый `<p role="status">` с текстом ожидания → `<Spinner label={…} />` с той же подписью;
- сообщения об успехе (например, «письмо отправлено») → `<Alert tone="success">`;
- оставшиеся `text-sm` → `text-small`, `text-xs` → `text-caption`.

На экране регистрации, если на нём тоже есть вход через Telegram или ключ доступа, поставить тот же разделитель, что и на входе, — дословно, включая `aria-hidden`.

- [ ] **Шаг 2: Убедиться, что тесты проходят**

Запустить: `pnpm --filter @repibot/web test "src/app/(auth)/"`
Ожидается: PASS. Если тест искал текст ожидания абзацем, а теперь его объявляет `Spinner` через `aria-label` — падение законно, перевести проверку на `getByRole('status', { name: … })`.

---

### Задача 5: Тарифы и карточка тарифа

**Файлы:**
- Изменить: `frontend/apps/web/src/app/plans/page.tsx`
- Изменить: `frontend/apps/web/src/components/plan-card.tsx`

**Интерфейсы:**
- Потребляет: `Alert`, `Spinner`, `Badge`.
- Отдаёт: ничего наружу.

В карточке тарифа есть самодельная плашка «пробный»: `rounded-full bg-jade-mist px-2.5 py-1 text-xs font-medium text-text-accent` (строка 81). Ровно то, ради чего появился `Badge`.

- [ ] **Шаг 1: Убедиться, что тесты сейчас зелёные**

Запустить: `pnpm --filter @repibot/web test src/app/plans/page.test.tsx src/components/plan-card.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 2: Привести страницу тарифов**

В `plans/page.tsx`:

- заголовок (строка 16) `text-3xl font-semibold tracking-[-0.02em]` → `text-h1 font-semibold`. Трекинг убрать: он уже есть в токене уровня, и второй раз задавать его на месте значит спорить с самим собой;
- загрузка (строки 19–21) → `<Spinner label={t('common.loading')} className="mt-10 block" />`;
- отказ (строки 23–32) — текст в `Alert tone="error"`, кнопка «Повторить» остаётся под ним внутри той же `Card`.

- [ ] **Шаг 3: Заменить плашку бейджем**

В `plan-card.tsx` (строка 81):

```tsx
          <Badge tone="info">{translate(language, 'plans.trial')}</Badge>
```

Ключ подписи взять тот же, что стоял в плашке раньше, — он уже в словаре.

- [ ] **Шаг 4: Привести карточку к шкале**

- строка 77: `text-xl font-semibold tracking-[-0.01em]` → `text-h2 font-semibold` (трекинг уже в токене);
- строка 88: `text-sm leading-6` → `text-small` (интерлиньяж уже в токене);
- строка 97: цена `text-3xl font-semibold tracking-[-0.02em]` → `text-h1 font-semibold`;
- строки 91, 100: `text-sm` → `text-small`;
- строки 111, 117: `text-xs` → `text-caption`;
- строки 112, 118: `text-lg font-medium` → `text-h3 font-medium`.

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Запустить: `pnpm --filter @repibot/web test src/app/plans/page.test.tsx src/components/plan-card.test.tsx`
Ожидается: PASS.

---

### Задача 6: Документ, отписка, возврат

**Файлы:**
- Изменить: `frontend/apps/web/src/app/legal/[slug]/page.tsx`
- Изменить: `frontend/apps/web/src/app/unsubscribe/page.tsx`
- Изменить: `frontend/apps/web/src/app/winback/page.tsx`

**Интерфейсы:**
- Потребляет: `Alert`, `Spinner`.
- Отдаёт: ничего наружу.

- [ ] **Шаг 1: Страница документа**

Заголовок → `text-h1 font-semibold`. Колонка остаётся `max-w-2xl` — это ширина чтения, и она уже верная.

Содержимое не трогать: страница остаётся заглушкой до отдельной работы, которая подключит тексты из таблицы. Обещание в комментарии наверху файла при этом устарело — подпроект 4 его не выполнил, — и комментарий надо поправить по факту, а не оставлять ссылку на несделанное:

```tsx
/**
 * Юридические документы. Содержимое поедет из таблицы legal_documents
 * отдельной работой; пока маршрут существует, чтобы ссылки в подвале
 * не вели в 404.
 */
```

- [ ] **Шаг 2: Страница отписки**

- строка 76: заголовок → `text-h1 font-semibold`;
- строка 83: `text-sm` → `text-small`;
- строка 88: отказ → `<Alert tone="error">`;
- строка 93: ссылка `text-sm` → `text-small`.

- [ ] **Шаг 3: Страница возврата**

- строка 56: заголовок → `text-h1 font-semibold`;
- строка 63: загрузка → `<Spinner label={translate(language, 'common.loading')} />`;
- строка 69: отказ → `<Alert tone="error">`;
- строка 74: ссылка `text-sm` → `text-small`.

- [ ] **Шаг 4: Убедиться, что тесты проходят**

Запустить: `pnpm --filter @repibot/web test src/app/winback/page.test.tsx`
Ожидается: PASS.

- [ ] **Шаг 5: Проверить всё своё разом**

Запустить: `pnpm --filter @repibot/web test "src/app/(auth)/" src/app/plans/ src/app/winback/ src/components/plan-card.test.tsx && pnpm --filter @repibot/web typecheck`
Ожидается: PASS обеих команд. Это последняя задача плана.
