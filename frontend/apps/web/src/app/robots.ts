import type { MetadataRoute } from 'next'

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      // Закрыто не ради секретности — эти адреса и так требуют сессии, — а
      // чтобы обходчик не тратил лимит на страницы, где ему нечего забрать.
      disallow: ['/account', '/admin', '/api'],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  }
}
