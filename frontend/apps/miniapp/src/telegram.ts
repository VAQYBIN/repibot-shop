/**
 * Тонкая обёртка над Telegram WebApp SDK.
 *
 * Обмен initData на токен появится в подпроекте 1. Здесь только чтение
 * и применение темы — этого достаточно, чтобы убедиться, что MiniApp
 * действительно открывается внутри Telegram.
 */

interface TelegramWebApp {
  initData?: string
  colorScheme?: 'light' | 'dark'
  ready?: () => void
  expand?: () => void
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
  }
}

function webApp(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp
}

export function readInitData(): string | null {
  const data = webApp()?.initData
  return data ? data : null
}

export function isInsideTelegram(): boolean {
  return readInitData() !== null
}

export function applyTelegramTheme(): void {
  const scheme = webApp()?.colorScheme
  if (!scheme) return
  document.documentElement.dataset.theme = scheme
}

export function initTelegram(): void {
  const app = webApp()
  app?.ready?.()
  app?.expand?.()
  applyTelegramTheme()
}
