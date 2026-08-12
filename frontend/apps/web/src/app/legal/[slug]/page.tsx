import { Card } from '@repibot/ui'

/**
 * Юридические документы. Содержимое поедет из таблицы legal_documents
 * отдельной работой; пока маршрут существует, чтобы ссылки в подвале
 * не вели в 404.
 */
export default async function LegalPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params

  return (
    <main className="mx-auto max-w-2xl p-6">
      <Card>
        <h1 className="text-h1 font-semibold">Документ: {slug}</h1>
        <p className="mt-2 text-text-secondary">Текст документа появится позже.</p>
      </Card>
    </main>
  )
}
