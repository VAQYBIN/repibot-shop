/**
 * Подпись initData и заглушка Telegram WebApp SDK для сквозного обхода MiniApp.
 *
 * Настоящего Телеграма в контуре нет: браузер Playwright открывает `/app/`
 * напрямую, и `window.Telegram` подставляется скриптом до первой отрисовки.
 */

import { createHmac } from 'node:crypto'

/** Токен подставного бота из stack.env. Секретом не является. */
const BOT_TOKEN = '0:e2e-bot-token'

/**
 * Подпись initData по правилам Telegram: ключ выводится HMAC-ом от токена
 * бота на строке "WebAppData", а подписью самого чек-стринга служит HMAC от
 * этого ключа. Поле hash в подсчёт не входит.
 *
 * Сверено с backend/core/src/repibot_core/security/initdata.py — там тот же
 * порядок: `secret = HMAC(key=b"WebAppData", msg=bot_token)`, затем
 * `hash = HMAC(key=secret, msg=check_string)`. У Node `createHmac(algo, key)`
 * первым аргументом конструктора берёт именно ключ, поэтому
 * `createHmac('sha256', 'WebAppData').update(BOT_TOKEN)` — это ровно
 * `HMAC(key="WebAppData", msg=BOT_TOKEN)`, то же самое выражение.
 */
export function signInitData(user: { id: number; username: string }): string {
  const fields: Record<string, string> = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: 'AAE',
    user: JSON.stringify({ id: user.id, first_name: 'E2E', username: user.username }),
  }

  const check = Object.keys(fields)
    .sort()
    .map((key) => `${key}=${fields[key]}`)
    .join('\n')
  const secret = createHmac('sha256', 'WebAppData').update(BOT_TOKEN).digest()
  const hash = createHmac('sha256', secret).update(check).digest('hex')

  return new URLSearchParams({ ...fields, hash }).toString()
}

/**
 * Форма заглушки под то, что читает `frontend/apps/miniapp/src/telegram.ts`.
 * `MainButton` обязателен целиком: без него обход прошёл бы по запасной
 * ветке с обычной кнопкой и не проверил бы ровно то, что переделано.
 */
export interface TelegramWebAppStub {
  initData: string
  initDataUnsafe: { user: { language_code: string } }
  colorScheme: 'light' | 'dark'
  ready: () => void
  expand: () => void
  openLink: () => void
  openTelegramLink: () => void
  onEvent: () => void
  offEvent: () => void
  MainButton: {
    setText: () => void
    show: () => void
    hide: () => void
    enable: () => void
    disable: () => void
    showProgress: () => void
    hideProgress: () => void
    onClick: () => void
    offClick: () => void
  }
  HapticFeedback: {
    notificationOccurred: () => void
    impactOccurred: () => void
  }
}

// Расширяет глобальный Window только в TS-программе web-пакета: у MiniApp
// своя, независимая — конфликта между ними нет.
declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebAppStub }
  }
}
