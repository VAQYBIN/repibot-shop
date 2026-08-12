'use client'

import { useMe } from '@repibot/core'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

/**
 * Главная админки.
 *
 * Сотруднику поддержки сводка не положена, а пустая главная выглядела бы
 * поломкой: он попадает туда, ради чего и открыл админку. Содержимое для
 * администратора заменит план сводки.
 */
export default function AdminPage() {
  const router = useRouter()
  const me = useMe()
  const support = me.data?.role === 'support'

  useEffect(() => {
    if (support) router.replace('/admin/users')
  }, [support, router])

  // Обещание сводки поддержке показывать нечего: редирект асинхронный, и без
  // этой проверки чужая главная мелькнула бы на экране.
  if (me.isPending || support) return null
  return <main className="p-6 text-text">Сводка появится в этом разделе.</main>
}
