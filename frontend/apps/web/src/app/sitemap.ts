import type { MetadataRoute } from 'next'

import { fetchFromApi } from '@/lib/server-api'

interface LegalListItem {
  slug: string
  title: string
  published_at: string
}

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost'

/**
 * Карта сайта: только то, что имеет смысл показывать поисковику.
 *
 * Кабинет, админка, вход и регистрация исключены: за ними ничего нет без
 * сессии, а их присутствие в карте — приглашение перебирать логины.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const documents = (await fetchFromApi<LegalListItem[]>('/api/legal')) ?? []

  return [
    { url: `${SITE_URL}/`, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE_URL}/plans`, changeFrequency: 'weekly', priority: 0.8 },
    ...documents.map((document) => ({
      url: `${SITE_URL}/legal/${document.slug}`,
      lastModified: new Date(document.published_at),
      changeFrequency: 'yearly' as const,
      priority: 0.3,
    })),
  ]
}
