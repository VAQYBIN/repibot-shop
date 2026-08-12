'use client'

import { useAuthClient, useMe } from '@repibot/core'
import { Button, Card, Dialog, EmptyState, Input } from '@repibot/ui'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import Link from 'next/link'
import { type ReactNode, use, useState } from 'react'

/** Действия модерации: один и тот же ответ `{changed}` у всех четырёх. */
type Moderation = 'block' | 'unblock' | 'mute' | 'unmute'

/** Что спрашиваем подтверждением. Оба действия необратимы для человека. */
type Confirmation = 'block' | 'revoke'

const STATUS_LABELS: Record<string, string> = {
  trial: 'Пробная',
  active: 'Активна',
  expired: 'Истекла',
  disabled: 'Отключена',
  pending_provision: 'Заводится',
}

const KIND_LABELS: Record<string, string> = {
  subscription: 'Подписка',
  payment: 'Оплата',
  staff: 'Персонал',
}

const DONE: Record<Moderation, string> = {
  block: 'Аккаунт заблокирован.',
  unblock: 'Аккаунт разблокирован.',
  mute: 'Поддержка для человека закрыта.',
  unmute: 'Поддержка для человека открыта.',
}

/**
 * `{"changed": false}` — не успех: сервис модерации так отвечает, когда менять
 * было нечего. Для сотрудника это значит, что коллега успел раньше, и
 * показывать ему «готово» было бы враньём.
 */
const UNCHANGED = 'Ничего не изменилось: коллега успел раньше.'

function moment(value: string): string {
  return new Date(value).toLocaleString('ru-RU')
}

function day(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU')
}

/**
 * Ответ сервера приходит телом `{"error": {"code", "message"}}`. Разбираем
 * только те коды, за которыми стоит разное поведение сотрудника: молчащую
 * панель имеет смысл переспросить, отказ по правам — нет.
 */
function errorMessage(error: unknown, fallback: string): string {
  const code = (error as { error?: { code?: string } } | null | undefined)?.error?.code
  if (code === 'panel_unavailable') return 'Панель не отвечает. Повторите попытку позже.'
  if (code === 'forbidden') return 'Для этого действия нужны права администратора.'
  if (code === 'not_found') return 'Пользователь не найден.'
  if (code === 'subscription_missing') return 'В панели этого человека ещё нет — выпускать нечего.'
  return fallback
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-text-muted text-xs">{label}</dt>
      <dd className="text-sm text-text">{children}</dd>
    </div>
  )
}

export default function AdminUserCardPage({ params }: { params: Promise<{ id: string }> }) {
  const userId = Number(use(params).id)
  const { api } = useAuthClient()
  const queries = useQueryClient()
  const me = useMe()
  // Роль берём оттуда же, откуда её берёт оболочка админки: из профиля, а не из
  // токена. Кнопка, которая всегда отвечает «нельзя», хуже отсутствующей —
  // поэтому деньги поддержке не показываются вовсе.
  const isAdmin = me.data?.role === 'admin'

  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [planId, setPlanId] = useState('')
  const [days, setDays] = useState('')
  const [comment, setComment] = useState('')

  const cardKey = ['admin', 'user', userId, 'card']
  const journalKey = ['admin', 'user', userId, 'journal']
  const devicesKey = ['admin', 'user', userId, 'devices']

  const card = useQuery({
    queryKey: cardKey,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/users/{user_id}', {
        params: { path: { user_id: userId } },
      })
      if (error || !data) throw error ?? new Error('пустая карточка пользователя')
      return data
    },
  })

  const journal = useQuery({
    queryKey: journalKey,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/users/{user_id}/journal', {
        params: { path: { user_id: userId } },
      })
      if (error || !data) throw error ?? new Error('пустой журнал пользователя')
      return data
    },
  })

  const devices = useQuery({
    queryKey: devicesKey,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/users/{user_id}/devices', {
        params: { path: { user_id: userId } },
      })
      if (error || !data) throw error ?? new Error('пустой список устройств')
      return data
    },
  })

  const plans = useQuery({
    queryKey: ['admin', 'plans'],
    // Тарифы нужны только форме начисления, а формы у поддержки нет: лишний
    // запрос ответил бы ей отказом и напугал бы красной строкой в консоли.
    enabled: isAdmin,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/plans')
      if (error || !data) throw error ?? new Error('пустой список тарифов')
      return data
    },
  })

  /**
   * После любого действия перечитываются карточка и журнал: решение персонала —
   * это событие ленты, и не показать его сразу значит заставить сотрудника
   * обновлять страницу руками.
   */
  async function refreshPerson(): Promise<void> {
    await Promise.all([
      queries.invalidateQueries({ queryKey: cardKey }),
      queries.invalidateQueries({ queryKey: journalKey }),
    ])
  }

  const moderate = useMutation({
    mutationFn: async (action: Moderation) => {
      const options = { params: { path: { user_id: userId } } }
      const result =
        action === 'block'
          ? await api.POST('/api/admin/users/{user_id}/block', options)
          : action === 'unblock'
            ? await api.POST('/api/admin/users/{user_id}/unblock', options)
            : action === 'mute'
              ? await api.POST('/api/admin/users/{user_id}/mute', options)
              : await api.POST('/api/admin/users/{user_id}/unmute', options)
      if (result.error || !result.data) throw result.error ?? new Error('пустой ответ модерации')
      return result.data.changed
    },
    onSuccess: async (changed, action) => {
      setConfirmation(null)
      setNotice(changed ? DONE[action] : UNCHANGED)
      await refreshPerson()
    },
  })

  const revoke = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        '/api/admin/users/{user_id}/subscription/revoke-link',
        { params: { path: { user_id: userId } } },
      )
      if (error || !data) throw error ?? new Error('пустой ответ панели')
      return data
    },
    onSuccess: async () => {
      setConfirmation(null)
      setNotice('Выпущена новая ссылка подписки. Старая больше не работает.')
      await refreshPerson()
    },
  })

  const unlink = useMutation({
    mutationFn: async (hwid: string) => {
      // Ответ 204: тела нет, разбирать нечего — только признак отказа.
      const { error } = await api.DELETE('/api/admin/users/{user_id}/devices/{hwid}', {
        params: { path: { user_id: userId, hwid } },
      })
      if (error) throw error
    },
    onSuccess: async () => {
      setNotice('Устройство отвязано.')
      await Promise.all([refreshPerson(), queries.invalidateQueries({ queryKey: devicesKey })])
    },
  })

  const grant = useMutation({
    mutationFn: async (withDays: boolean) => {
      const { error } = await api.POST('/api/admin/users/{user_id}/subscription', {
        params: { path: { user_id: userId } },
        body: {
          plan_id: Number(planId),
          days: withDays ? Number(days) : null,
          comment: comment.trim() === '' ? null : comment.trim(),
        },
      })
      if (error) throw error
    },
    onSuccess: async (_result, withDays) => {
      setNotice(withDays ? 'Дни начислены.' : 'Тариф изменён.')
      setDays('')
      setComment('')
      await refreshPerson()
    },
  })

  const actionError = moderate.error ?? revoke.error ?? unlink.error ?? grant.error
  const busy = moderate.isPending || revoke.isPending || unlink.isPending || grant.isPending
  const numericDays = Number(days)
  const daysReady = planId !== '' && days.trim() !== '' && Number.isSafeInteger(numericDays)

  if (card.isPending) {
    return <main className="p-6 text-sm text-text-secondary">Загрузка…</main>
  }
  if (card.error !== null) {
    return (
      <main className="p-6">
        <p role="alert" className="text-danger text-sm">
          {errorMessage(card.error, 'Не удалось загрузить карточку пользователя.')}
        </p>
      </main>
    )
  }

  const row = card.data.row
  const person = row.name ?? row.email ?? `#${row.id}`

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6 text-text">
      <header>
        <p className="text-sm text-text-secondary">
          <Link href="/admin/users" className="underline-offset-2 hover:underline">
            ← К списку пользователей
          </Link>
        </p>
        <h1 className="mt-2 font-semibold text-2xl">{person}</h1>
        <p className="mt-1 text-sm text-text-muted">{`#${row.id}`}</p>
      </header>

      <section aria-labelledby="who-heading">
        <Card>
          <h2 id="who-heading" className="font-semibold text-lg text-text">
            Кто это
          </h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Почта">
              {row.email === null ? (
                '—'
              ) : (
                <>
                  <span className="break-all">{row.email}</span>{' '}
                  <span className="text-text-muted text-xs">
                    {card.data.email_verified ? 'подтверждена' : 'не подтверждена'}
                  </span>
                </>
              )}
            </Field>
            <Field label="Telegram">
              {row.telegram_username === null
                ? (row.telegram_id ?? '—')
                : `@${row.telegram_username}`}
            </Field>
            <Field label="Язык">{card.data.language}</Field>
            <Field label="Роль">{card.data.role}</Field>
            <Field label="Регистрация">{moment(card.data.created_at)}</Field>
            <Field label="Пригласил">
              {card.data.referred_by_id === null ? (
                '—'
              ) : (
                <Link
                  href={`/admin/users/${card.data.referred_by_id}`}
                  className="underline-offset-2 hover:underline"
                >
                  {`#${card.data.referred_by_id}`}
                </Link>
              )}
            </Field>
          </dl>
        </Card>
      </section>

      <section aria-labelledby="subscription-heading">
        <Card>
          <h2 id="subscription-heading" className="font-semibold text-lg text-text">
            Подписка
          </h2>
          <dl className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label="Тариф">{row.plan_name ?? '—'}</Field>
            <Field label="Состояние">
              {row.subscription_status === null
                ? 'Нет подписки'
                : (STATUS_LABELS[row.subscription_status] ?? row.subscription_status)}
            </Field>
            <Field label="Действует до">
              {row.expires_at === null ? '—' : day(row.expires_at)}
            </Field>
            <Field label="Автопродление">{card.data.auto_renew ? 'Включено' : 'Выключено'}</Field>
            <Field label="Источник">{card.data.subscription_source ?? '—'}</Field>
            <Field label="Номер в панели">{card.data.remnawave_id ?? '—'}</Field>
          </dl>

          <p className="mt-4 text-text-muted text-xs">Ссылка подписки</p>
          <p className="mt-1 break-all text-sm text-text">{card.data.subscription_url ?? '—'}</p>

          <h3 className="mt-6 font-semibold text-base text-text">Устройства</h3>
          {devices.isPending ? (
            <p className="mt-2 text-sm text-text-secondary">Загрузка…</p>
          ) : devices.error !== null ? (
            // Молчащая панель гасит только этот блок: карточку она уронить не
            // может, потому что устройства просит отдельный запрос.
            <div className="mt-2 flex flex-col items-start gap-2">
              <p role="alert" className="text-danger text-sm">
                {errorMessage(devices.error, 'Не удалось получить список устройств.')}
              </p>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={devices.isFetching}
                onClick={() => devices.refetch()}
              >
                Повторить
              </Button>
            </div>
          ) : devices.data.devices.length === 0 ? (
            <EmptyState className="mt-2" title="Устройств нет" />
          ) : (
            <>
              <p className="mt-2 text-sm text-text-secondary">
                {`Занято ${devices.data.used} из ${devices.data.limit}`}
              </p>
              <ul aria-label="Устройства" className="mt-2 flex flex-col gap-2">
                {devices.data.devices.map((device) => {
                  const label = device.device_model ?? device.platform ?? device.hwid
                  return (
                    <li
                      key={device.hwid}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-surface-sunken p-3"
                    >
                      <div>
                        <p className="text-sm text-text">{label}</p>
                        <p className="text-text-muted text-xs">
                          {[device.platform, device.os_version, moment(device.created_at)]
                            .filter((part) => part !== null)
                            .join(' · ')}
                        </p>
                      </div>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        aria-label={`Отвязать ${label}`}
                        disabled={busy}
                        onClick={() => unlink.mutate(device.hwid)}
                      >
                        Отвязать
                      </Button>
                    </li>
                  )
                })}
              </ul>
            </>
          )}
        </Card>
      </section>

      <section aria-labelledby="actions-heading">
        <Card>
          <h2 id="actions-heading" className="font-semibold text-lg text-text">
            Действия
          </h2>

          {notice === null ? null : (
            <p role="status" className="mt-2 text-sm text-text-secondary">
              {notice}
            </p>
          )}
          {actionError === null || actionError === undefined ? null : (
            <p role="alert" className="mt-2 text-danger text-sm">
              {errorMessage(actionError, 'Действие не выполнено.')}
            </p>
          )}

          <div className="mt-4 flex flex-wrap gap-3">
            {row.banned ? (
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => moderate.mutate('unblock')}
              >
                Разблокировать
              </Button>
            ) : (
              // Блокировка спрашивает подтверждение: человек по ту сторону
              // теряет и покупки, и разговор, и узнает об этом сам.
              <Button type="button" disabled={busy} onClick={() => setConfirmation('block')}>
                Заблокировать
              </Button>
            )}

            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => moderate.mutate(row.support_muted ? 'unmute' : 'mute')}
            >
              {row.support_muted ? 'Открыть поддержку' : 'Закрыть поддержку'}
            </Button>

            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => setConfirmation('revoke')}
            >
              Выпустить новую ссылку
            </Button>
          </div>

          {isAdmin ? (
            <div className="mt-6 border-border-subtle border-t pt-6">
              <h3 className="font-semibold text-base text-text">Дни и тариф</h3>
              <p className="mt-1 max-w-prose text-sm text-text-secondary">
                Отрицательное число дней снимает срок. Смена тарифа пересчитывает оплаченный
                остаток.
              </p>

              <label htmlFor="grant-plan" className="mt-4 block font-medium text-sm text-text">
                Тариф
              </label>
              <select
                id="grant-plan"
                value={planId}
                onChange={(event) => setPlanId(event.target.value)}
                className="mt-2 h-10 w-full rounded-md border border-border-subtle bg-surface px-3 text-text focus:border-accent focus:outline-none focus:ring-3 focus:ring-jade-mist"
              >
                <option value="">Выберите тариф</option>
                {(plans.data ?? []).map((plan) => (
                  <option key={plan.id} value={String(plan.id)}>
                    {plan.name.ru ?? plan.code}
                  </option>
                ))}
              </select>

              <label htmlFor="grant-days" className="mt-4 block font-medium text-sm text-text">
                Дни
              </label>
              <Input
                id="grant-days"
                type="number"
                className="mt-2"
                value={days}
                onChange={(event) => setDays(event.target.value)}
              />

              <label htmlFor="grant-comment" className="mt-4 block font-medium text-sm text-text">
                Комментарий
              </label>
              <Input
                id="grant-comment"
                className="mt-2"
                value={comment}
                onChange={(event) => setComment(event.target.value)}
              />

              <div className="mt-4 flex flex-wrap gap-3">
                <Button
                  type="button"
                  disabled={busy || !daysReady}
                  onClick={() => grant.mutate(true)}
                >
                  Выдать дни
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={busy || planId === ''}
                  onClick={() => grant.mutate(false)}
                >
                  Сменить тариф
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
      </section>

      <section aria-labelledby="journal-heading">
        <Card>
          <h2 id="journal-heading" className="font-semibold text-lg text-text">
            Журнал
          </h2>
          {journal.isPending ? (
            <p className="mt-4 text-sm text-text-secondary">Загрузка…</p>
          ) : journal.error !== null ? (
            <p role="alert" className="mt-4 text-danger text-sm">
              {errorMessage(journal.error, 'Не удалось загрузить журнал.')}
            </p>
          ) : journal.data.length === 0 ? (
            <EmptyState className="mt-4" title="Событий пока нет" />
          ) : (
            <ol aria-label="Журнал" className="mt-4 flex flex-col gap-3">
              {journal.data.map((item) => (
                <li
                  key={`${item.at}-${item.kind}-${item.title}`}
                  className="rounded-md bg-surface-sunken p-3"
                >
                  <p className="text-text-muted text-xs">
                    {`${moment(item.at)} · ${KIND_LABELS[item.kind] ?? item.kind}`}
                    {item.actor === null ? ' · система' : ` · ${item.actor}`}
                  </p>
                  <p className="mt-1 text-sm text-text">{item.title}</p>
                  {item.detail === null ? null : (
                    <p className="mt-1 text-sm text-text-secondary">{item.detail}</p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </Card>
      </section>

      <Dialog
        open={confirmation === 'block'}
        onClose={() => setConfirmation(null)}
        title="Заблокировать аккаунт?"
        description="Человек потеряет вход, покупки и переписку с поддержкой. Разблокировать придётся вручную."
      >
        <Button type="button" variant="secondary" onClick={() => setConfirmation(null)}>
          Отмена
        </Button>
        <Button type="button" disabled={busy} onClick={() => moderate.mutate('block')}>
          Да, заблокировать
        </Button>
      </Dialog>

      <Dialog
        open={confirmation === 'revoke'}
        onClose={() => setConfirmation(null)}
        title="Выпустить новую ссылку подписки?"
        description="Старая ссылка перестанет работать на всех устройствах человека, и вернуть её нельзя."
      >
        <Button type="button" variant="secondary" onClick={() => setConfirmation(null)}>
          Отмена
        </Button>
        <Button type="button" disabled={busy} onClick={() => revoke.mutate()}>
          Да, выпустить
        </Button>
      </Dialog>
    </main>
  )
}
