'use client'

import { useAuthClient, useMe } from '@repibot/core'
import {
  Alert,
  Badge,
  Button,
  Card,
  Dialog,
  EmptyState,
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from '@repibot/ui'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { AdminPage } from '@/components/admin-page'

interface Selection {
  slug: string
  locale: string
}

interface Draft {
  title: string
  content: string
}

const EMPTY_DRAFT: Draft = { title: '', content: '' }

/** Те же локали, что принимает бэкенд: маршрут отвергает всё остальное. */
const LOCALES: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'ru', label: 'Русский' },
  { value: 'en', label: 'English' },
]

const ERRORS: Record<string, string> = {
  draft_not_found: 'Публиковать нечего: правок после последней публикации не было.',
  not_found: 'Документ не найден. Возможно, его сняли или ещё не сохраняли.',
  validation_error: 'Имя документа — строчные латинские буквы, цифры и дефис, от двух символов.',
  invalid_source: 'Принимаются только ссылки на telegra.ph.',
  import_failed: 'Telegra.ph не ответил. Повторите позже или вставьте текст руками.',
  forbidden: 'Юридические документы доступны только администратору.',
}

/** Ответ об ошибке приходит телом `{"error": {"code", "message"}}`. */
function errorText(error: unknown, fallback: string): string {
  const code = (error as { error?: { code?: string } } | null | undefined)?.error?.code
  return (code === undefined ? undefined : ERRORS[code]) ?? fallback
}

function formatMoment(value: string | null): string {
  return value === null ? '—' : new Date(value).toLocaleString('ru-RU')
}

function LegalScreen() {
  const { api } = useAuthClient()
  const queries = useQueryClient()
  const [selected, setSelected] = useState<Selection | null>(null)
  // Открытая версия. null — текущая правка документа, число — строка истории.
  const [version, setVersion] = useState<number | null>(null)
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT)
  const [sourceUrl, setSourceUrl] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newSlug, setNewSlug] = useState('')
  const [newLocale, setNewLocale] = useState('ru')
  const [withdrawing, setWithdrawing] = useState(false)

  const documents = useQuery({
    queryKey: ['admin', 'legal'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/admin/legal')
      if (error || !data) throw error ?? new Error('пустой список документов')
      return data
    },
  })

  const document = useQuery({
    queryKey: ['admin', 'legal', selected?.slug, selected?.locale, version],
    enabled: selected !== null,
    queryFn: async () => {
      const current = selected as Selection
      if (version !== null) {
        const { data, error } = await api.GET(
          '/api/admin/legal/{slug}/{locale}/versions/{version}',
          { params: { path: { ...current, version } } },
        )
        if (error || !data) throw error ?? new Error('пустая версия документа')
        return data
      }

      const { data, error } = await api.GET('/api/admin/legal/{slug}/{locale}', {
        params: { path: current },
      })
      // Заведённый, но ни разу не сохранённый документ — не ошибка: админ
      // только что открыл его пустым и сейчас наберёт текст.
      if (error && (error as { error?: { code?: string } }).error?.code === 'not_found') return null
      if (error || !data) throw error ?? new Error('пустой документ')
      return data
    },
  })

  const versions = useQuery({
    queryKey: ['admin', 'legal-versions', selected?.slug, selected?.locale],
    enabled: selected !== null,
    queryFn: async () => {
      const current = selected as Selection
      const { data, error } = await api.GET('/api/admin/legal/{slug}/{locale}/versions', {
        params: { path: current },
      })
      if (error || !data) throw error ?? new Error('пустая история версий')
      return data
    },
  })

  // Поля наполняются из ответа, а не из первого нажатия: то же место открывает
  // и текущую правку, и старую версию, и только что заведённый пустой документ.
  const loaded = document.data
  useEffect(() => {
    if (loaded === undefined) return
    setDraft(loaded === null ? EMPTY_DRAFT : { title: loaded.title, content: loaded.content })
  }, [loaded])

  async function invalidate(): Promise<void> {
    await Promise.all([
      queries.invalidateQueries({ queryKey: ['admin', 'legal'] }),
      queries.invalidateQueries({ queryKey: ['admin', 'legal-versions'] }),
    ])
  }

  const save = useMutation({
    mutationFn: async () => {
      const current = selected as Selection
      const { error } = await api.PUT('/api/admin/legal/{slug}/{locale}', {
        params: { path: current },
        body: { title: draft.title, content: draft.content },
      })
      if (error) throw error
    },
    onSuccess: async () => {
      setVersion(null)
      setNotice('Черновик сохранён. Посетители его пока не видят.')
      await invalidate()
    },
  })

  const publish = useMutation({
    mutationFn: async () => {
      const current = selected as Selection
      const { error } = await api.POST('/api/admin/legal/{slug}/{locale}/publish', {
        params: { path: current },
      })
      if (error) throw error
    },
    onSuccess: async () => {
      setVersion(null)
      setNotice('Документ опубликован — он открыт всем посетителям.')
      await invalidate()
    },
  })

  const withdraw = useMutation({
    mutationFn: async () => {
      const current = selected as Selection
      const { error } = await api.DELETE('/api/admin/legal/{slug}/{locale}', {
        params: { path: current },
      })
      if (error) throw error
    },
    onSuccess: async () => {
      setWithdrawing(false)
      setNotice('Документ снят с публикации. Текст и история сохранены.')
      await invalidate()
    },
  })

  const load = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/admin/legal/import', {
        body: { url: sourceUrl },
      })
      if (error || !data) throw error ?? new Error('пустой ответ импорта')
      return data
    },
    // Загруженное только подставляется в поля: сохраняет админ, посмотрев его.
    onSuccess: (page) => setDraft({ title: page.title, content: page.content }),
  })

  function open(next: Selection) {
    setSelected(next)
    setVersion(null)
    setNotice(null)
    // Ссылку набирали для другого документа: переносить её опаснее, чем терять.
    setSourceUrl('')
  }

  const items = documents.data ?? []
  const busy = save.isPending || publish.isPending || withdraw.isPending
  const ready = draft.title.trim() !== '' && draft.content.trim() !== ''

  return (
    <AdminPage
      title="Юридические документы"
      description="Тексты соглашения, политики и оферты. Публикуются сразу после нажатия."
      actions={<Button onClick={() => setCreating(true)}>Новый документ</Button>}
    >
      <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
        <section aria-labelledby="legal-list-heading">
          <Card>
            <h2 id="legal-list-heading" className="font-medium text-h3 text-text">
              Документы
            </h2>

            {documents.isPending ? (
              <div className="mt-4">
                <Spinner label="Загрузка" />
              </div>
            ) : documents.error !== null ? (
              <Alert tone="error" className="mt-4">
                {errorText(documents.error, 'Не удалось загрузить список документов.')}
              </Alert>
            ) : items.length === 0 ? (
              <EmptyState
                className="mt-4"
                title="Документов пока нет"
                description="Заведите соглашение, политику или оферту — текст можно загрузить с Telegra.ph."
                action={<Button onClick={() => setCreating(true)}>Новый документ</Button>}
              />
            ) : (
              <ul aria-label="Документы" className="mt-4 flex flex-col gap-2">
                {items.map((item) => (
                  <li key={`${item.slug}:${item.locale}`}>
                    <button
                      type="button"
                      aria-pressed={
                        item.slug === selected?.slug && item.locale === selected?.locale
                      }
                      onClick={() => open({ slug: item.slug, locale: item.locale })}
                      className="w-full rounded-md border border-border-subtle px-3 py-2 text-left aria-pressed:border-accent aria-pressed:bg-surface-sunken"
                    >
                      <span className="block truncate font-medium text-small text-text">
                        {item.title === '' ? item.slug : item.title}
                      </span>
                      <span className="mt-1 flex flex-wrap items-center gap-2 text-caption text-text-muted">
                        {`${item.slug} · ${item.locale}`}
                        {item.published_version === null || item.withdrawn ? (
                          <Badge tone="neutral">Не опубликован</Badge>
                        ) : (
                          <Badge tone="success">{`Версия ${item.published_version}`}</Badge>
                        )}
                        {item.has_draft ? <Badge tone="warning">Черновик</Badge> : null}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </section>

        <section aria-labelledby="legal-editor-heading" className="flex flex-col gap-6">
          <Card>
            <h2 id="legal-editor-heading" className="font-medium text-h3 text-text">
              Редактор
            </h2>

            {selected === null ? (
              <EmptyState className="mt-4" title="Выберите документ слева" />
            ) : (
              <>
                <p className="mt-1 text-small text-text-secondary">
                  {`${selected.slug} · ${selected.locale}`}
                </p>

                {version === null ? null : (
                  <Alert tone="info" className="mt-4">
                    {`Открыта версия ${version}. Сохранение положит её текст в новую правку.`}
                  </Alert>
                )}

                <div className="mt-4 grid gap-3">
                  <FormField label="Заголовок" htmlFor="legal-title">
                    <Input
                      id="legal-title"
                      value={draft.title}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, title: event.target.value }))
                      }
                    />
                  </FormField>

                  <FormField
                    label="Ссылка на Telegra.ph"
                    htmlFor="legal-source"
                    hint="Загрузка только подставляет текст в поля — сохраняете и публикуете вы сами."
                  >
                    <Input
                      id="legal-source"
                      value={sourceUrl}
                      onChange={(event) => setSourceUrl(event.target.value)}
                    />
                  </FormField>

                  <div>
                    <Button
                      variant="secondary"
                      disabled={sourceUrl.trim() === '' || load.isPending}
                      onClick={() => void load.mutateAsync()}
                    >
                      Загрузить
                    </Button>
                  </div>

                  {load.error === null ? null : (
                    // Набранный текст при этом остаётся на месте: ошибка загрузки
                    // не повод стирать то, что человек уже написал.
                    <Alert tone="error">
                      {errorText(load.error, 'Не удалось загрузить страницу.')}
                    </Alert>
                  )}
                </div>

                <Tabs defaultValue="text" className="mt-4 block">
                  <TabsList>
                    <TabsTrigger value="text">Текст</TabsTrigger>
                    <TabsTrigger value="preview">Предпросмотр</TabsTrigger>
                  </TabsList>

                  <TabsContent value="text">
                    <FormField
                      label="Текст документа (Markdown)"
                      htmlFor="legal-content"
                      hint="Заголовки — ##, списки — дефисом. Разметку разбирает сервер."
                    >
                      <Textarea
                        id="legal-content"
                        rows={18}
                        value={draft.content}
                        onChange={(event) =>
                          setDraft((current) => ({ ...current, content: event.target.value }))
                        }
                      />
                    </FormField>
                  </TabsContent>

                  <TabsContent value="preview">
                    {document.data === undefined || document.data === null ? (
                      <p className="text-small text-text-secondary">
                        Предпросмотр появится после первого сохранения.
                      </p>
                    ) : (
                      <>
                        <p className="text-small text-text-muted">
                          Показан сохранённый текст: несохранённые правки сюда ещё не попали.
                        </p>
                        <div
                          className="mt-4 flex flex-col gap-4 text-body text-text-secondary [&_a]:text-text-accent [&_a]:underline [&_h2]:mt-6 [&_h2]:font-semibold [&_h2]:text-h2 [&_h2]:text-text [&_h3]:mt-4 [&_h3]:font-medium [&_h3]:text-h3 [&_h3]:text-text [&_li]:ml-5 [&_li]:list-disc [&_ol_li]:list-decimal"
                          // biome-ignore lint/security/noDangerouslySetInnerHtml: HTML собран и очищен на бэкенде, см. repibot_core.content.markdown
                          dangerouslySetInnerHTML={{ __html: document.data.html }}
                        />
                      </>
                    )}
                  </TabsContent>
                </Tabs>

                {document.error === null ? null : (
                  <Alert tone="error" className="mt-4">
                    {errorText(document.error, 'Не удалось загрузить документ.')}
                  </Alert>
                )}
                {save.error === null ? null : (
                  <Alert tone="error" className="mt-4">
                    {errorText(save.error, 'Не удалось сохранить черновик.')}
                  </Alert>
                )}
                {publish.error === null ? null : (
                  <Alert tone="error" className="mt-4">
                    {errorText(publish.error, 'Не удалось опубликовать документ.')}
                  </Alert>
                )}
                {withdraw.error === null ? null : (
                  <Alert tone="error" className="mt-4">
                    {errorText(withdraw.error, 'Не удалось снять документ с публикации.')}
                  </Alert>
                )}
                {notice === null ? null : (
                  <Alert tone="success" className="mt-4">
                    {notice}
                  </Alert>
                )}

                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <Button disabled={!ready || busy} onClick={() => void save.mutateAsync()}>
                    Сохранить черновик
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() => void publish.mutateAsync()}
                  >
                    Опубликовать
                  </Button>
                  <Button variant="secondary" disabled={busy} onClick={() => setWithdrawing(true)}>
                    Снять с публикации
                  </Button>
                </div>
              </>
            )}
          </Card>

          {selected === null ? null : (
            <Card>
              <h2 className="font-medium text-h3 text-text">История версий</h2>
              {versions.isPending ? (
                <div className="mt-4">
                  <Spinner label="Загрузка" />
                </div>
              ) : versions.error !== null ? (
                <Alert tone="error" className="mt-4">
                  {errorText(versions.error, 'Не удалось загрузить историю версий.')}
                </Alert>
              ) : versions.data.length === 0 ? (
                <p className="mt-4 text-small text-text-secondary">Версий пока нет.</p>
              ) : (
                <div className="mt-4">
                  <Table caption="Версии документа">
                    <TableHead>
                      <TableRow>
                        <TableHeaderCell>Версия</TableHeaderCell>
                        <TableHeaderCell>Опубликована</TableHeaderCell>
                        <TableHeaderCell>Снята</TableHeaderCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {versions.data.map((item) => (
                        <TableRow key={item.version}>
                          <TableCell>
                            {/* Кнопкой, а не нажатием по строке: строка таблицы
                                не получает фокус с клавиатуры. */}
                            <Button variant="ghost" onClick={() => setVersion(item.version)}>
                              {`Версия ${item.version}`}
                            </Button>
                          </TableCell>
                          <TableCell>{formatMoment(item.published_at)}</TableCell>
                          <TableCell>{formatMoment(item.withdrawn_at)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </Card>
          )}
        </section>
      </div>

      <Dialog
        open={creating}
        onClose={() => setCreating(false)}
        title="Новый документ"
        description="Имя попадёт в адрес страницы: /legal/terms. Поменять его потом нельзя."
      >
        <div className="flex w-full flex-col gap-3">
          <FormField label="Имя документа" htmlFor="new-slug">
            <Input
              id="new-slug"
              value={newSlug}
              onChange={(event) => setNewSlug(event.target.value)}
            />
          </FormField>
          <FormField label="Язык" htmlFor="new-locale">
            <Select
              id="new-locale"
              value={newLocale}
              onChange={(event) => setNewLocale(event.target.value)}
            >
              {LOCALES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
          </FormField>
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={() => setCreating(false)}>
              Отмена
            </Button>
            <Button
              disabled={newSlug.trim() === ''}
              onClick={() => {
                open({ slug: newSlug.trim(), locale: newLocale })
                setDraft(EMPTY_DRAFT)
                setNewSlug('')
                setCreating(false)
              }}
            >
              Открыть редактор
            </Button>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={withdrawing}
        onClose={() => setWithdrawing(false)}
        title="Снять с публикации?"
        description="Страница документа сразу перестанет открываться посетителям. Текст и история версий останутся на месте."
      >
        <Button variant="secondary" onClick={() => setWithdrawing(false)}>
          Отмена
        </Button>
        <Button disabled={withdraw.isPending} onClick={() => void withdraw.mutateAsync()}>
          Снять с публикации
        </Button>
      </Dialog>
    </AdminPage>
  )
}

/**
 * Юридические тексты — только для администратора.
 *
 * Оболочка админки пускает и поддержку, но API ответит ей 403. Честный отказ
 * до нажатия кнопки лучше, чем редактор, сохранение из которого заведомо не
 * пройдёт.
 */
export default function AdminLegalPage() {
  const me = useMe()
  if (me.data === undefined) return null
  if (me.data.role !== 'admin') {
    return (
      <AdminPage title="Юридические документы">
        <p className="max-w-prose text-small text-text-secondary">
          Раздел доступен только администратору: условия продажи меняет тот, кто за них отвечает.
        </p>
      </AdminPage>
    )
  }
  return <LegalScreen />
}
