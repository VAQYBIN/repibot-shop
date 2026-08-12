import { Card } from '@repibot/ui'

import { Lockup } from '@/components/lockup'

// Переключателя темы здесь больше нет: он переехал в шапку публичной
// оболочки. Двух одинаковых кнопок на одной странице не должно быть — на
// вторую наткнулся бы и человек, и строгий поиск по имени в e2e.
export default function HomePage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col justify-center gap-6 p-6">
      <Lockup size={48} />
      <Card>
        <h1 className="text-h1 font-semibold">Магазин ещё готовится</h1>
        <p className="mt-2 text-text-secondary">
          Здесь появятся тарифы, подписка и личный кабинет.
        </p>
      </Card>
    </main>
  )
}
