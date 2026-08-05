import { Card } from '@repibot/ui'
import type { ReactNode } from 'react'

import { Lockup } from '@/components/lockup'

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center gap-6 p-6">
      <Lockup size={40} />
      <Card>{children}</Card>
    </main>
  )
}
