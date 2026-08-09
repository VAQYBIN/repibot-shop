import { describe, expect, it } from 'vitest'

import { errorMessageKey } from './errors'

describe('errorMessageKey', () => {
  it.each([
    ['panel_unavailable', 'error.panel_unavailable'],
    ['device_not_found', 'error.device_not_found'],
    ['subscription_missing', 'error.subscription_missing'],
    ['trial_already_used', 'error.trial_already_used'],
    ['trial_requires_telegram', 'error.trial_requires_telegram'],
    ['trial_disabled', 'error.trial_disabled'],
    ['subscription_exists', 'error.subscription_exists'],
    ['subscription_not_found', 'payment.error.subscription_not_found'],
  ] as const)('переводит новый код %s в ключ словаря', (code, key) => {
    expect(errorMessageKey(code)).toBe(key)
  })
})
