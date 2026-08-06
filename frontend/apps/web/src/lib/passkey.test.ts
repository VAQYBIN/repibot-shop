import { describe, expect, it } from 'vitest'

import { passkeyErrorKey } from './passkey'

describe('passkeyErrorKey', () => {
  it('отличает отмену пользователем от настоящей ошибки', () => {
    const cancelled = new Error('отменено')
    cancelled.name = 'NotAllowedError'

    expect(passkeyErrorKey(cancelled)).toBe('auth.error.passkey_cancelled')
  })

  it('код ошибки бэкенда превращает в свой ключ', () => {
    expect(passkeyErrorKey({ error: { code: 'last_login_method' } })).toBe(
      'auth.error.last_login_method',
    )
  })

  it('незнакомую ошибку показывает общим сообщением', () => {
    expect(passkeyErrorKey(new Error('что-то не так'))).toBe('auth.error.unknown')
  })
})
