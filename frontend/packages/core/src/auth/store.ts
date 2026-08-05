/**
 * Access-токен живёт в памяти и нигде больше.
 *
 * localStorage отпадает по двум причинам: в веб-версии Telegram наш домен
 * оказывается в стороннем контексте, а любая XSS читает его одной строкой.
 * Плата за это — перезагрузка страницы теряет токен и вызывает refresh.
 */
export interface TokenStore {
  get(): string | null
  set(token: string | null): void
  subscribe(listener: () => void): () => void
}

export function createTokenStore(): TokenStore {
  let token: string | null = null
  const listeners = new Set<() => void>()

  return {
    get: () => token,
    set(next) {
      token = next
      for (const listener of listeners) listener()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
}
