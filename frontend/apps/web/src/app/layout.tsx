import { TooltipProvider } from '@repibot/ui'
import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { AuthProvider } from '@/components/auth-provider'
import { BrowserPreferencesProvider } from '@/lib/browser-preferences'

import './globals.css'

export const metadata: Metadata = {
  title: 'Re:Pibot',
  description: 'Магазин VPN-подписок',
  manifest: '/manifest.webmanifest',
  // SVG первым: браузеры, которые его понимают, растр даже не запросят.
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon-32.png', sizes: '32x32', type: 'image/png' },
      { url: '/favicon-16.png', sizes: '16x16', type: 'image/png' },
    ],
    apple: '/icon-192.png',
  },
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>
        {/* Browser preferences определяют язык и тему после гидратации;
            API-клиент и его токен остаются одним экземпляром. */}
        <BrowserPreferencesProvider>
          <AuthProvider>
            {/* Подсказкам Radix нужен один общий провайдер на приложение:
                он держит задержку появления и следит, чтобы две подсказки
                не всплыли разом. */}
            <TooltipProvider delayDuration={300}>{children}</TooltipProvider>
          </AuthProvider>
        </BrowserPreferencesProvider>
      </body>
    </html>
  )
}
