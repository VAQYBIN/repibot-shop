'use client'

import { useAuthClient, useMe } from '@repibot/core'
import { Alert, Card, Skeleton, Tabs, TabsList, TabsTrigger } from '@repibot/ui'
import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'

import { AdminPage } from '@/components/admin-page'

type Period = 'today' | 'week' | 'month'

/**
 * Периоды сводки. Подпись плитки повторяет выбранный период: числа за день и
 * за месяц выглядят одинаково, и без подписи их не различить.
 */
const PERIODS: readonly { value: Period; label: string; caption: string }[] = [
  { value: 'today', label: 'Сегодня', caption: 'За сегодня' },
  { value: 'week', label: '7 дней', caption: 'За последние 7 дней' },
  { value: 'month', label: '30 дней', caption: 'За последние 30 дней' },
]

/** Подпись плиток, которых выбранный период не касается. */
const NOW = 'Сейчас, независимо от периода'

/** Плиток в сводке шесть — ровно столько же заглушек нужно на время загрузки. */
const SKELETON_TILES = [0, 1, 2, 3, 4, 5] as const

/** Разряды и знак рубля отделяем неразрывным пробелом: число не должно рваться переносом. */
const NBSP = ' '

/**
 * Выручка приходит строкой и строкой же доходит до экрана.
 *
 * Через `Number` её вести нельзя: у десятичной суммы с копейками нет точного
 * представления в двоичной дроби, и на большой выручке округление показало бы
 * не ту копейку. Разбор строки этого не допускает.
 */
function formatRevenue(value: string): string {
  const [whole, fraction] = value.split('.')
  const grouped = (whole ?? '0').replace(/\B(?=(\d{3})+$)/g, NBSP)
  // Ровные рубли показываем без копеек: «,00» в каждой сумме только шумит.
  const kopecks = fraction === undefined || /^0*$/.test(fraction) ? '' : `,${fraction}`
  return `${grouped}${kopecks}${NBSP}₽`
}

interface TileProps {
  label: string
  value: string
  caption: string
  /** Адрес, если плитка ведёт на другой экран. */
  href?: string
}

function Tile({ label, value, caption, href }: TileProps) {
  // Плитка названа целиком: иначе число «3» звучит само по себе, в отрыве от
  // того, чего именно три.
  const card: ReactNode = (
    <Card aria-label={label} className="h-full" role="group">
      <p className="text-small text-text-secondary">{label}</p>
      {/* Число крупнее подписи вдвое: в сводке первым читается оно. */}
      <p className="mt-2 font-semibold text-h1 text-text">{value}</p>
      <p className="mt-1 text-caption text-text-muted">{caption}</p>
    </Card>
  )

  if (href === undefined) return card
  return (
    <Link
      href={href}
      className="rounded-lg focus-visible:ring-3 focus-visible:ring-jade-mist focus-visible:outline-none"
    >
      {card}
    </Link>
  )
}

/**
 * Главная админки — сводка за выбранный период.
 *
 * Сотруднику поддержки сводка не положена, а пустая главная выглядела бы
 * поломкой: он попадает туда, ради чего и открыл админку.
 */
export default function AdminMetricsPage() {
  const router = useRouter()
  const me = useMe()
  const { api } = useAuthClient()
  const [period, setPeriod] = useState<Period>('today')
  const support = me.data?.role === 'support'

  useEffect(() => {
    if (support) router.replace('/admin/users')
  }, [support, router])

  const metrics = useQuery({
    queryKey: ['admin', 'metrics', period],
    // Маршрут отвечает поддержке отказом, поэтому запрос уходит, только когда
    // роль известна и это администратор.
    enabled: me.data?.role === 'admin',
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/metrics', { params: { query: { period } } })
      if (error || !data) throw error ?? new Error('пустая сводка')
      return data
    },
  })

  // Сводку поддержке показывать нечего: редирект асинхронный, и без этой
  // проверки чужая главная мелькнула бы на экране.
  if (me.isPending || support) return null

  const shown = metrics.data
  // Пока чисел нет, плитки говорят об этом прямо: ноль выручки и неизвестная
  // выручка выглядят одинаково, но значат разное.
  const unknown = metrics.error === null ? 'Загрузка…' : '—'
  const count = (value: number | undefined): string =>
    value === undefined ? unknown : String(value)
  const caption = PERIODS.find((option) => option.value === period)?.caption ?? ''

  return (
    <AdminPage
      title="Сводка"
      description="Деньги и подписки по нашей базе. Границы периодов считаются по UTC, как и всё остальное время в системе."
    >
      {/* Период живёт в состоянии страницы, адрес раздела от него не зависит —
          вкладки, а не ссылки. */}
      <Tabs value={period} onValueChange={(next) => setPeriod(next as Period)}>
        <TabsList aria-label="Период">
          {PERIODS.map((option) => (
            <TabsTrigger key={option.value} value={option.value}>
              {option.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {metrics.error === null ? null : <Alert tone="error">Не удалось загрузить сводку.</Alert>}

      {metrics.isPending ? (
        // Заглушки по форме плиток: сетка не должна прыгать, когда числа
        // приедут.
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SKELETON_TILES.map((key) => (
            <Skeleton key={key} className="h-28 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Tile
            label="Выручка"
            value={shown === undefined ? unknown : formatRevenue(shown.revenue_rub)}
            caption={caption}
          />
          <Tile label="Оплаты" value={count(shown?.payments)} caption={caption} />
          <Tile label="Новые подписки" value={count(shown?.new_subscriptions)} caption={caption} />
          <Tile label="Продления" value={count(shown?.renewals)} caption={caption} />
          <Tile
            label="Активные подписки"
            value={count(shown?.active_subscriptions)}
            caption={NOW}
          />
          <Tile
            label="Ждут ответа"
            value={count(shown?.tickets_waiting)}
            caption={NOW}
            href="/admin/tickets"
          />
        </div>
      )}
    </AdminPage>
  )
}
