/**
 * Тонкая обёртка над Telegram WebApp SDK.
 *
 * Обмен initData на токен появится в подпроекте 1. Здесь только чтение
 * и применение темы — этого достаточно, чтобы убедиться, что MiniApp
 * действительно открывается внутри Telegram.
 */

interface TelegramWebApp {
  initData?: string
  initDataUnsafe?: { user?: { language_code?: string } }
  colorScheme?: 'light' | 'dark'
  ready?: () => void
  expand?: () => void
  openLink?: (url: string) => void
  openTelegramLink?: (url: string) => void
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

/**
 * Порядок предпочтений языка: сначала выставленный Telegram, затем настройки
 * браузера. Значение берётся из initDataUnsafe и используется только для
 * выбора языка — оно не подписано, и доверять ему что-то важнее нельзя.
 */
export function preferredLanguages(): readonly string[] {
  const fromTelegram = webApp()?.initDataUnsafe?.user?.language_code
  const fromBrowser = navigator.languages ?? [navigator.language]
  return fromTelegram ? [fromTelegram, ...fromBrowser] : fromBrowser
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

/** Платёжные переходы остаются внутри Telegram WebView, а не создают вкладку. */
export function openTelegramUrl(url: string, botLink = false): void {
  const app = webApp()
  if (botLink) app?.openTelegramLink?.(url)
  else app?.openLink?.(url)
}
