import { translate } from '@repibot/core'
import { notFound } from 'next/navigation'

import { fetchFromApi } from '@/lib/server-api'

interface LegalDocument {
  slug: string
  title: string
  html: string
  locale: string
  version: number
  published_at: string
}

/**
 * Юридический документ.
 *
 * Собирается на сервере: страница входит в карту сайта, и её содержимое
 * должно доставаться поисковику, а не появляться после гидратации.
 *
 * HTML вставляется как есть, потому что он собран и очищен на бэкенде.
 * Второй очистки на фронте нет намеренно: два набора правил разъезжаются,
 * и однажды сюда попадёт то, что прошло одну проверку и не прошло другую.
 */
export default async function LegalPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const document = await fetchFromApi<LegalDocument>(`/api/legal/${slug}`)

  if (document === null) notFound()

  return (
    <main className="mx-auto w-full max-w-2xl px-6 py-12">
      <h1 className="font-semibold text-h1 text-text">{document.title}</h1>
      <p className="mt-2 text-small text-text-muted">
        {translate('ru', 'legal.effective_from').replace(
          '{date}',
          new Date(document.published_at).toLocaleDateString('ru-RU'),
        )}
      </p>
      <div
        className="mt-8 flex flex-col gap-4 text-body text-text-secondary [&_a]:text-text-accent [&_a]:underline [&_h2]:mt-6 [&_h2]:font-semibold [&_h2]:text-h2 [&_h2]:text-text [&_h3]:mt-4 [&_h3]:font-medium [&_h3]:text-h3 [&_h3]:text-text [&_li]:ml-5 [&_li]:list-disc [&_ol_li]:list-decimal"
        // biome-ignore lint/security/noDangerouslySetInnerHtml: HTML собран и очищен на бэкенде, см. repibot_core.content.markdown
        dangerouslySetInnerHTML={{ __html: document.html }}
      />
    </main>
  )
}
