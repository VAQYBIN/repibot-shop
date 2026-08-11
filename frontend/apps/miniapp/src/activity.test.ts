import { focusManager } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { trackTelegramActivity } from './activity'

afterEach(() => {
  vi.unstubAllGlobals()
  focusManager.setFocused(undefined)
})

describe('активность Mini App в кэше запросов', () => {
  it('переносит события Telegram в признак активности кэша', () => {
    /* Кэш сам знает только про видимость документа, а Mini App при уходе в
       браузер не скрывается — свернувшего его Telegram приходится пересказать. */
    const handlers = new Map<string, () => void>()
    vi.stubGlobal('Telegram', {
      WebApp: {
        initData: 'x',
        onEvent: (event: string, handler: () => void) => handlers.set(event, handler),
        offEvent: (event: string) => handlers.delete(event),
      },
    })

    trackTelegramActivity()

    handlers.get('deactivated')?.()
    expect(focusManager.isFocused()).toBe(false)
    handlers.get('activated')?.()
    expect(focusManager.isFocused()).toBe(true)
  })
})
