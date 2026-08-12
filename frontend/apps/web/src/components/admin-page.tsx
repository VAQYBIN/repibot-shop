import type { ReactNode } from 'react'

export interface AdminPageProps {
  title: string
  description?: string | undefined
  /** Кнопки справа от заголовка: обновить, создать, выгрузить. */
  actions?: ReactNode
  children: ReactNode
}

/**
 * Общий образец страницы админки: заголовок, действия справа, содержимое.
 *
 * Живёт здесь, а не в `packages/ui`: это устройство одного раздела, а не
 * приём интерфейса вообще. В кабинете страницы устроены иначе, и общий
 * компонент на оба случая пришлось бы разводить свойствами до неузнаваемости.
 *
 * Описание не обязательно, но заголовок обязателен: сквозной обход экранов
 * падает на странице без заголовка первого уровня — пустая разметка из-за
 * упавшего запроса иначе выглядит просто как «ничего нет».
 */
export function AdminPage({ title, description, actions, children }: AdminPageProps) {
  return (
    <main className="flex flex-col gap-6 px-6 py-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-semibold text-h1 text-text">{title}</h1>
          {description === undefined ? null : (
            <p className="mt-1 max-w-prose text-small text-text-secondary">{description}</p>
          )}
        </div>
        {actions === undefined ? null : <div className="shrink-0">{actions}</div>}
      </div>

      {children}
    </main>
  )
}
