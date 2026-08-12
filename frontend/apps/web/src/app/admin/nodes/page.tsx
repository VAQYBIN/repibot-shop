'use client'

import { formatBytes, useAuthClient } from '@repibot/core'
import { Alert, Badge, type BadgeTone, Button, Card, EmptyState, Spinner } from '@repibot/ui'
import { useQuery } from '@tanstack/react-query'

import { AdminPage } from '@/components/admin-page'

/**
 * Состояние узла меняется само, а открывают эту страницу ровно тогда, когда
 * ждут изменений: подняли ноду, перезапустили Xray, ждут возврата связи.
 * Без опроса дежурный узнавал бы об этом перезагрузкой страницы.
 */
const NODES_POLL_MS = 30_000

/**
 * Ответ об отказе приходит телом `{"error": {"code", "message"}}`. Молчащая
 * или отказавшая панель — это `panel_unavailable`: с нашей стороны всё цело,
 * и повторить попытку осмысленно.
 */
function errorText(error: unknown): string {
  const code = (error as { error?: { code?: string } } | null | undefined)?.error?.code
  if (code === 'panel_unavailable') {
    return 'Панель не ответила — состояние узлов неизвестно. Это не значит, что узлы выключены.'
  }
  return 'Не удалось получить список узлов.'
}

interface NodeState {
  label: string
  tone: BadgeTone
}

/**
 * Выключенная нода и потерявшая связь — разные события: первую выключил
 * человек, вторая отвалилась сама. Показать их одинаково значит будить
 * дежурного из-за плановых работ, поэтому выключение проверяется первым:
 * выключенная нода и не должна быть на связи.
 */
function nodeState(node: { is_disabled: boolean; is_connected: boolean }): NodeState {
  if (node.is_disabled) return { label: 'Выключена', tone: 'neutral' }
  if (!node.is_connected) return { label: 'Нет связи', tone: 'danger' }
  return { label: 'На связи', tone: 'success' }
}

/** Адрес без порта панель отдаёт, когда узел ещё не настроен до конца. */
function addressLabel(address: string, port: number | null): string {
  return port === null ? address : `${address}:${port}`
}

/**
 * Нулевой лимит у панели означает «без ограничения». Написать «0 Б» — сказать
 * ровно обратное: что трафик исчерпан.
 */
function trafficLabel(used: number, limit: number): string {
  const spent = formatBytes(used, 'ru')
  return limit === 0 ? `${spent} / без лимита` : `${spent} / ${formatBytes(limit, 'ru')}`
}

/**
 * Время работы Xray: часы и минуты, дни отдельно. Секунды в разговоре о
 * непрерывной работе не значат ничего, а ноль значит, что Xray не работает.
 */
function uptimeLabel(seconds: number): string {
  if (seconds <= 0) return 'Xray не запущен'

  const days = Math.floor(seconds / 86_400)
  const hours = Math.floor((seconds % 86_400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days > 0) return `${days} дн ${hours} ч`
  if (hours > 0) return `${hours} ч ${minutes} мин`
  return `${minutes} мин`
}

export default function AdminNodesPage() {
  const { api } = useAuthClient()

  const nodes = useQuery({
    queryKey: ['admin', 'nodes'],
    refetchInterval: NODES_POLL_MS,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/nodes')
      if (error || !data) throw error ?? new Error('пустой список узлов')
      return data
    },
  })

  return (
    <AdminPage
      title="Ноды"
      description="Состояние узлов панели, только просмотр. Список сам обновляется раз в полминуты, включать и перезапускать узлы отсюда нельзя."
    >
      {nodes.isPending ? (
        <Spinner label="Загружаем узлы" />
      ) : nodes.error !== null ? (
        // Пустой список вместо отказа читался бы как «узлов нет», а узлы
        // просто не спросили: показываем причину и даём повторить.
        <Card>
          <Alert tone="error">{errorText(nodes.error)}</Alert>
          <Button
            className="mt-4"
            variant="secondary"
            disabled={nodes.isFetching}
            onClick={() => void nodes.refetch()}
          >
            Повторить
          </Button>
        </Card>
      ) : nodes.data.length === 0 ? (
        <EmptyState title="Панель не знает ни одного узла." />
      ) : (
        <ul aria-label="Узлы" className="flex flex-col gap-4">
          {nodes.data.map((item) => {
            const state = nodeState(item)
            return (
              <li key={`${item.address}:${item.port ?? ''}:${item.name}`}>
                <article aria-label={item.name}>
                  <Card>
                    <div className="flex flex-wrap items-baseline justify-between gap-3">
                      <h2 className="text-h3 font-medium text-text">
                        {item.name}
                        <span className="ml-2 text-small font-normal text-text-muted">
                          {item.country_code}
                        </span>
                      </h2>
                      <Badge tone={state.tone}>{state.label}</Badge>
                    </div>

                    {/* Последнее сообщение о состоянии — сразу под именем:
                        читают его только когда что-то не так. */}
                    {item.last_status_message === null ? null : (
                      <p className="mt-1 text-small break-words text-text-secondary">
                        {item.last_status_message}
                      </p>
                    )}

                    <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-small sm:grid-cols-4">
                      <div>
                        <dt className="text-text-muted">Адрес</dt>
                        <dd className="mt-1 break-all text-text">
                          {addressLabel(item.address, item.port)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-text-muted">Людей онлайн</dt>
                        <dd className="mt-1 text-text tabular-nums">{item.users_online}</dd>
                      </div>
                      <div>
                        <dt className="text-text-muted">Трафик</dt>
                        <dd className="mt-1 text-text tabular-nums">
                          {trafficLabel(item.traffic_used_bytes, item.traffic_limit_bytes)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-text-muted">Xray работает</dt>
                        <dd className="mt-1 text-text tabular-nums">
                          {uptimeLabel(item.xray_uptime_seconds)}
                        </dd>
                      </div>
                    </dl>
                  </Card>
                </article>
              </li>
            )
          })}
        </ul>
      )}
    </AdminPage>
  )
}
