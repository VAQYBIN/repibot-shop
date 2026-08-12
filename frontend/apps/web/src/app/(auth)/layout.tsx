import type { ReactNode } from 'react'

import { Lockup } from '@/components/lockup'

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-sm flex-col justify-center gap-8 p-6">
      {/* Знак на всех шести экранах: человек попадает сюда по ссылке из
          письма и должен видеть, куда именно он попал. */}
      <Lockup size={32} />
      {children}
    </main>
  )
}
