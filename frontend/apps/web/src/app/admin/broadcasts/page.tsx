'use client'

import { useAuthClient, useMe } from '@repibot/core'
import {
  Alert,
  Badge,
  type BadgeTone,
  Button,
  Card,
  Dialog,
  FormField,
  Input,
  Select,
  Spinner,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
  Textarea,
} from '@repibot/ui'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { AdminPage } from '@/components/admin-page'

interface Broadcast {
  id: number
  segment: string
  title: Record<string, string>
  body: Record<string, string>
  status: string
  planned_count: number
  sent_count: number
  failed_count: number
  started_at: string | null
  finished_at: string | null
}

/** Готовые сегменты бэкенда. Отдельный тариф задаётся формой `plan:<код>`. */
const SEGMENTS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'all', label: 'Все пользователи' },
  { value: 'active', label: 'С активной подпиской' },
  { value: 'expired', label: 'С истёкшей подпиской' },
  { value: 'never_paid', label: 'Ни разу не платили' },
  { value: 'trial', label: 'На пробном периоде' },
  { value: 'plan', label: 'Отдельный тариф' },
]

const STATUSES: Record<string, string> = {
  draft: 'Черновик',
  running: 'Идёт',
  canceled: 'Отменена',
  done: 'Завершена',
}

/** Состояние кампании тоном: черновик нейтрален, идущее — заметно, конец — по исходу. */
const STATUS_TONES: Record<string, BadgeTone> = {
  draft: 'neutral',
  running: 'info',
  canceled: 'danger',
  done: 'success',
}

function statusTone(status: string): BadgeTone {
  return STATUS_TONES[status] ?? 'neutral'
}

const ERRORS: Record<string, string> = {
  broadcast_busy: 'Уже идёт другая кампания. Дождитесь её окончания или отмените её.',
  broadcast_not_draft: 'Кампанию уже запускали. Обновите страницу, чтобы увидеть её состояние.',
  broadcast_not_running: 'Кампания уже не идёт. Обновите страницу, чтобы увидеть её состояние.',
  unknown_segment: 'Такого сегмента нет. Проверьте код тарифа.',
  broadcast_text_required: 'Заголовок и текст по-русски обязательны.',
  forbidden: 'Рассылки доступны только администратору.',
}

/** Ответ об ошибке приходит как `{"error": {"code", "message"}}`. */
function errorText(error: unknown): string {
  const code = (error as { error?: { code?: string } })?.error?.code
  return (code && ERRORS[code]) || 'Не удалось выполнить операцию. Повторите попытку.'
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Не удалось выполнить операцию.'
}

function segmentLabel(segment: string): string {
  if (segment.startsWith('plan:')) return `Тариф ${segment.slice('plan:'.length)}`
  return SEGMENTS.find((item) => item.value === segment)?.label ?? segment
}

function statusLabel(status: string): string {
  return STATUSES[status] ?? status
}

/**
 * Охват сегмента. Единственная защита от «отправил не тем»: число получателей
 * видно до запуска, а не после него.
 */
function useSegmentReach(segment: string) {
  const { api } = useAuthClient()
  return useQuery({
    queryKey: ['admin', 'segment-count', segment],
    enabled: segment !== '',
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/segments/{segment}/count', {
        params: { path: { segment } },
      })
      if (error || !data) throw new Error(errorText(error))
      return data.count
    },
  })
}

function BroadcastsScreen() {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  const [segmentKind, setSegmentKind] = useState('')
  const [planCode, setPlanCode] = useState('')
  const [titleRu, setTitleRu] = useState('')
  const [bodyRu, setBodyRu] = useState('')
  const [titleEn, setTitleEn] = useState('')
  const [bodyEn, setBodyEn] = useState('')
  const [confirming, setConfirming] = useState<Broadcast | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const trimmedPlan = planCode.trim()
  const segment =
    segmentKind === 'plan' ? (trimmedPlan === '' ? '' : `plan:${trimmedPlan}`) : segmentKind

  const campaigns = useQuery({
    queryKey: ['admin', 'broadcasts'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/broadcasts')
      if (error || !data) throw new Error(errorText(error))
      return data as Broadcast[]
    },
    // Пока кампания идёт, счётчики меняются на сервере: без опроса прогресс
    // пришлось бы узнавать перезагрузкой страницы. На прочих статусах числа
    // уже окончательные, и опрос выключается сам.
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === 'running') ? 5000 : false,
  })

  const formReach = useSegmentReach(segment)
  const confirmReach = useSegmentReach(confirming?.segment ?? '')

  const create = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST('/api/admin/broadcasts', {
        body: {
          segment,
          // Русский текст обязателен: он же запасной для всех прочих языков.
          title: titleEn.trim() === '' ? { ru: titleRu } : { ru: titleRu, en: titleEn },
          body: bodyEn.trim() === '' ? { ru: bodyRu } : { ru: bodyRu, en: bodyEn },
        },
      })
      if (error) throw new Error(errorText(error))
    },
    onSuccess: async () => {
      setTitleRu('')
      setBodyRu('')
      setTitleEn('')
      setBodyEn('')
      setNotice('Черновик создан. Проверьте охват и запустите его из списка.')
      await queries.invalidateQueries({ queryKey: ['admin', 'broadcasts'] })
    },
  })

  const start = useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.POST('/api/admin/broadcasts/{broadcast_id}/start', {
        params: { path: { broadcast_id: id } },
      })
      if (error) throw new Error(errorText(error))
    },
    onSuccess: async () => {
      setConfirming(null)
      setNotice('Рассылка запущена. Счётчики обновляются сами.')
      await queries.invalidateQueries({ queryKey: ['admin', 'broadcasts'] })
    },
  })

  const cancel = useMutation({
    mutationFn: async (id: number) => {
      const { error } = await api.POST('/api/admin/broadcasts/{broadcast_id}/cancel', {
        params: { path: { broadcast_id: id } },
      })
      if (error) throw new Error(errorText(error))
    },
    onSuccess: async () => {
      setNotice('Рассылка остановлена. Уже отправленные сообщения не отзываются.')
      await queries.invalidateQueries({ queryKey: ['admin', 'broadcasts'] })
    },
  })

  const ready = segment !== '' && titleRu.trim() !== '' && bodyRu.trim() !== ''
  const items = campaigns.data ?? []

  return (
    <AdminPage
      title="Рассылки"
      description="Сообщение уходит в Telegram всем, кто попал в сегмент. Проверьте охват до запуска: отправку можно остановить, но доставленное не отзывается."
    >
      <section aria-labelledby="campaigns-heading">
        <Card>
          <h2 id="campaigns-heading" className="font-medium text-h3 text-text">
            Кампании
          </h2>
          {campaigns.error === null ? null : (
            <Alert tone="error" className="mt-3">
              {messageOf(campaigns.error)}
            </Alert>
          )}
          {campaigns.isPending ? (
            <div className="mt-3">
              <Spinner label="Загружаем кампании" />
            </div>
          ) : items.length === 0 ? (
            <p className="mt-3 text-small text-text-secondary">Кампаний пока нет.</p>
          ) : (
            <div className="mt-4">
              <Table caption="Кампании">
                <TableHead>
                  <TableRow>
                    <TableHeaderCell>Заголовок</TableHeaderCell>
                    <TableHeaderCell>Сегмент</TableHeaderCell>
                    <TableHeaderCell>Статус</TableHeaderCell>
                    <TableHeaderCell>Запланировано</TableHeaderCell>
                    <TableHeaderCell>Отправлено</TableHeaderCell>
                    <TableHeaderCell>Ошибок</TableHeaderCell>
                    <TableHeaderCell>Действие</TableHeaderCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{item.title.ru ?? `Кампания №${item.id}`}</TableCell>
                      <TableCell>{segmentLabel(item.segment)}</TableCell>
                      <TableCell>
                        <Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge>
                      </TableCell>
                      <TableCell className="tabular-nums">{item.planned_count}</TableCell>
                      <TableCell className="tabular-nums">{item.sent_count}</TableCell>
                      <TableCell className="tabular-nums">{item.failed_count}</TableCell>
                      <TableCell>
                        {item.status === 'draft' ? (
                          <Button variant="secondary" onClick={() => setConfirming(item)}>
                            Запустить
                          </Button>
                        ) : null}
                        {item.status === 'running' ? (
                          <Button
                            variant="secondary"
                            disabled={cancel.isPending}
                            onClick={() => void cancel.mutateAsync(item.id)}
                          >
                            Отменить
                          </Button>
                        ) : null}
                        {item.status === 'draft' || item.status === 'running' ? null : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {cancel.error === null ? null : (
            <Alert tone="error" className="mt-3">
              {messageOf(cancel.error)}
            </Alert>
          )}
        </Card>
      </section>

      <section aria-labelledby="new-broadcast-heading">
        <Card>
          <h2 id="new-broadcast-heading" className="font-medium text-h3 text-text">
            Новая рассылка
          </h2>
          <p className="mt-1 text-small text-text-secondary">
            Черновик никуда не уходит до запуска. Английский текст необязателен: без него всем уйдёт
            русский.
          </p>
          <div className="mt-4 grid gap-3">
            <FormField
              label="Сегмент"
              htmlFor="segment"
              hint={
                segment === ''
                  ? 'Охват появится после выбора сегмента.'
                  : formReach.isPending
                    ? 'Считаем охват сегмента…'
                    : formReach.error === null
                      ? `Охват сегмента: ${formReach.data}`
                      : messageOf(formReach.error)
              }
            >
              <Select
                id="segment"
                value={segmentKind}
                onChange={(event) => setSegmentKind(event.target.value)}
              >
                <option value="">Выберите сегмент</option>
                {SEGMENTS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </Select>
            </FormField>
            {segmentKind === 'plan' ? (
              <FormField label="Код тарифа" htmlFor="plan-code">
                <Input
                  id="plan-code"
                  value={planCode}
                  onChange={(event) => setPlanCode(event.target.value)}
                  className="max-w-xs"
                />
              </FormField>
            ) : null}
            <FormField label="Заголовок по-русски" htmlFor="title-ru">
              <Input
                id="title-ru"
                value={titleRu}
                onChange={(event) => setTitleRu(event.target.value)}
              />
            </FormField>
            <FormField label="Текст по-русски" htmlFor="body-ru">
              <Textarea
                id="body-ru"
                rows={4}
                value={bodyRu}
                onChange={(event) => setBodyRu(event.target.value)}
              />
            </FormField>
            <FormField label="Заголовок по-английски" htmlFor="title-en">
              <Input
                id="title-en"
                value={titleEn}
                onChange={(event) => setTitleEn(event.target.value)}
              />
            </FormField>
            <FormField label="Текст по-английски" htmlFor="body-en">
              <Textarea
                id="body-en"
                rows={4}
                value={bodyEn}
                onChange={(event) => setBodyEn(event.target.value)}
              />
            </FormField>
          </div>
          {create.error === null ? null : (
            <Alert tone="error" className="mt-3">
              {messageOf(create.error)}
            </Alert>
          )}
          <Button
            className="mt-4"
            disabled={!ready || create.isPending}
            onClick={() => void create.mutateAsync()}
          >
            Создать черновик
          </Button>
        </Card>
      </section>

      {notice === null ? null : <Alert tone="success">{notice}</Alert>}

      <Dialog
        open={confirming !== null}
        onClose={() => setConfirming(null)}
        title="Запустить рассылку?"
        description={
          confirmReach.isPending
            ? 'Считаем, скольким людям уйдёт сообщение…'
            : confirmReach.error === null
              ? `Сообщение уйдёт ${confirmReach.data} получателям сегмента «${segmentLabel(confirming?.segment ?? '')}». Остановить отправку можно, но доставленное не отзывается.`
              : messageOf(confirmReach.error)
        }
      >
        <Button variant="secondary" onClick={() => setConfirming(null)}>
          Отмена
        </Button>
        <Button
          // Запуск без известного охвата — то самое «отправил не тем»,
          // от которого экран и защищает.
          disabled={confirmReach.data === undefined || start.isPending}
          onClick={() => confirming !== null && void start.mutateAsync(confirming.id)}
        >
          Запустить рассылку
        </Button>
      </Dialog>
    </AdminPage>
  )
}

/**
 * Рассылки — только для администратора.
 *
 * Гейт раздела пускает и поддержку, но API ответит ей 403. Честный отказ до
 * нажатия кнопки лучше, чем форма, которая заведомо не сработает.
 */
export default function AdminBroadcastsPage() {
  const me = useMe()
  if (me.data === undefined) return null
  if (me.data.role !== 'admin') {
    return (
      <AdminPage title="Рассылки">
        <p className="max-w-prose text-small text-text-secondary">
          Раздел доступен только администратору. Если рассылка нужна, попросите её запустить того, у
          кого есть права.
        </p>
      </AdminPage>
    )
  }
  return <BroadcastsScreen />
}
