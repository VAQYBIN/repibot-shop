'use client'

import { useAuthClient } from '@repibot/core'
import { Button, Card, EmptyState, Input } from '@repibot/ui'
import { useInfiniteQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { useEffect, useState } from 'react'

/** Страница выдачи из спецификации: двадцать строк, дальше кнопка «ещё». */
const PAGE_SIZE = 20

/**
 * Задержка ввода.
 *
 * Строку набирают целиком — почту или @имя, — а поиск идёт сразу по трём
 * числовым полям и двум текстовым. Запрос на каждую букву означал бы десяток
 * заведомо ненужных поисков подряд.
 */
const SEARCH_DELAY_MS = 300

const STATUS_LABELS: Record<string, string> = {
  trial: 'Пробная',
  active: 'Активна',
  expired: 'Истекла',
  disabled: 'Отключена',
  pending_provision: 'Заводится',
}

type Row = {
  id: number
  name: string | null
  email: string | null
  telegram_id: number | null
  telegram_username: string | null
  plan_name: string | null
  subscription_status: string | null
  expires_at: string | null
  banned: boolean
  support_muted: boolean
}

/** Имя, почта или хотя бы номер: строка без подписи ни на что не нажимается. */
function personLabel(row: Row): string {
  return row.name ?? row.email ?? `#${row.id}`
}

function telegramLabel(row: Row): string {
  if (row.telegram_username !== null) return `@${row.telegram_username}`
  return row.telegram_id === null ? '—' : String(row.telegram_id)
}

function subscriptionLabel(row: Row): string {
  if (row.subscription_status === null) return 'Нет'
  const status = STATUS_LABELS[row.subscription_status] ?? row.subscription_status
  if (row.expires_at === null) return status
  return `${status} · до ${new Date(row.expires_at).toLocaleDateString('ru-RU')}`
}

/**
 * Ответ сервера приходит телом `{"error": {"code", "message"}}`. Отдельно
 * называем только отказ по правам: он значит, что дальше пробовать нечего.
 */
function errorMessage(error: unknown, fallback: string): string {
  const code = (error as { error?: { code?: string } } | null | undefined)?.error?.code
  if (code === 'forbidden') return 'Раздел доступен поддержке и администратору.'
  return fallback
}

export default function AdminUsersPage() {
  const { api } = useAuthClient()
  const [term, setTerm] = useState('')
  const [query, setQuery] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => setQuery(term), SEARCH_DELAY_MS)
    return () => clearTimeout(timer)
  }, [term])

  const users = useInfiniteQuery({
    queryKey: ['admin', 'users', query],
    initialPageParam: 0,
    // Смещением, а не курсором: людей в базе тысячи, а не миллионы, и вторая
    // страница нужна редко. Неполная страница означает, что просить нечего.
    getNextPageParam: (last: Row[], pages: Row[][]) =>
      last.length < PAGE_SIZE ? undefined : pages.length * PAGE_SIZE,
    queryFn: async ({ pageParam }) => {
      const { data, error } = await api.GET('/api/admin/users', {
        params: { query: { query, limit: PAGE_SIZE, offset: pageParam } },
      })
      if (error || !data) throw error ?? new Error('пустой список пользователей')
      return data
    },
  })

  const rows = users.data?.pages.flat() ?? []

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6 text-text">
      <header>
        <h1 className="font-semibold text-2xl">Пользователи</h1>
        <p className="mt-1 max-w-prose text-sm text-text-secondary">
          Одна строка на все опознаватели: почта, @имя, номер Telegram, аккаунта или панели.
          Разбирает её сервер — выбирать поле руками не нужно.
        </p>
      </header>

      <Card>
        <label htmlFor="user-search" className="font-medium text-sm text-text">
          Поиск
        </label>
        <Input
          id="user-search"
          className="mt-2"
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="vasya@example.com, @vasya, 700001"
        />

        {users.isPending ? (
          <p className="mt-4 text-sm text-text-secondary">Загрузка…</p>
        ) : users.error !== null ? (
          <p role="alert" className="mt-4 text-danger text-sm">
            {errorMessage(users.error, 'Не удалось загрузить список пользователей.')}
          </p>
        ) : rows.length === 0 ? (
          <EmptyState
            className="mt-4"
            title="Никого не нашли"
            description={
              query === ''
                ? 'В базе пока нет ни одного человека.'
                : 'Проверьте строку поиска: почта и имя ищутся по вхождению, номера — целиком.'
            }
          />
        ) : (
          <>
            <div className="mt-4 overflow-x-auto">
              <table aria-label="Пользователи" className="w-full text-left text-sm">
                <thead>
                  <tr className="text-text-muted text-xs">
                    <th scope="col" className="py-2 pr-3 font-medium">
                      Кто
                    </th>
                    <th scope="col" className="py-2 pr-3 font-medium">
                      Telegram
                    </th>
                    <th scope="col" className="py-2 pr-3 font-medium">
                      Тариф
                    </th>
                    <th scope="col" className="py-2 pr-3 font-medium">
                      Подписка
                    </th>
                    <th scope="col" className="py-2 font-medium">
                      Ограничения
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-border-subtle border-t align-top">
                      <td className="py-2 pr-3">
                        <Link
                          href={`/admin/users/${row.id}`}
                          className="font-medium text-text underline-offset-2 hover:underline"
                        >
                          {personLabel(row)}
                        </Link>
                        <span className="block text-text-muted text-xs">{`#${row.id}`}</span>
                      </td>
                      <td className="py-2 pr-3 text-text-secondary">{telegramLabel(row)}</td>
                      <td className="py-2 pr-3 text-text-secondary">{row.plan_name ?? '—'}</td>
                      <td className="py-2 pr-3 text-text-secondary">{subscriptionLabel(row)}</td>
                      <td className="py-2">
                        {/* Отметки — единственное, что видно про ограничения из
                            списка: подпись у них словами, значок один не читается
                            ни экранным диктором, ни новым сотрудником. */}
                        {row.banned ? (
                          <span role="img" aria-label="Заблокирован" title="Заблокирован">
                            ⛔
                          </span>
                        ) : null}
                        {row.support_muted ? (
                          <span role="img" aria-label="Поддержка закрыта" title="Поддержка закрыта">
                            🔇
                          </span>
                        ) : null}
                        {row.banned || row.support_muted ? null : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {users.hasNextPage ? (
              <Button
                type="button"
                variant="secondary"
                className="mt-4"
                disabled={users.isFetchingNextPage}
                onClick={() => users.fetchNextPage()}
              >
                Показать ещё
              </Button>
            ) : null}
          </>
        )}
      </Card>
    </main>
  )
}
