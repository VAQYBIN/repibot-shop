import { Card } from '@repibot/ui'

import { Lockup } from '@/components/lockup'
import { ThemeToggle } from '@/components/theme-toggle'

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-6 p-6">
      <Lockup size={48} />
      <Card>
        <h1 className="text-h1 font-semibold">Магазин ещё готовится</h1>
        <p className="mt-2 text-text-secondary">
          Здесь появятся тарифы, подписка и личный кабинет.
        </p>
      </Card>
      <ThemeToggle />
    </main>
  )
}
