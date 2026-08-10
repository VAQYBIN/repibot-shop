import { NextRequest } from 'next/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { proxy } from './proxy'

const SECRET = '0123456789abcdef0123456789abcdef'
// Produced independently by the Python backend HMAC-SHA256 format:
// {"exp":4070908800,"role":"admin","v":1}.
const VALID_ASSERTION =
  'eyJleHAiOjQwNzA5MDg4MDAsInJvbGUiOiJhZG1pbiIsInYiOjF9.hJE-ubRMPQgduamsjWC_2beA2lseC7LqBBcvAIp1Kmo'
const EXPIRED_ASSERTION =
  'eyJleHAiOjEsInJvbGUiOiJhZG1pbiIsInYiOjF9.PZp8pev_4rlLzhhA4NuqwRqixN9eO9x7jNy5StLdk7Y'

function adminRequest(assertion?: string): NextRequest {
  const headers = assertion === undefined ? {} : { cookie: `repibot_admin_assertion=${assertion}` }
  return new NextRequest('https://example.org/admin/payments', { headers })
}

describe('admin payments server gate', () => {
  beforeEach(() => vi.stubEnv('ADMIN_ASSERTION_SECRET', SECRET))
  afterEach(() => vi.unstubAllEnvs())

  it('redirects a direct request without an assertion before rendering payments', () => {
    const response = proxy(adminRequest())

    expect(response.headers.get('location')).toBe('https://example.org/login')
  })

  it('allows an independently backend-signed admin assertion', () => {
    const response = proxy(adminRequest(VALID_ASSERTION))

    expect(response.headers.get('location')).toBeNull()
  })

  it('rejects a tampered assertion before rendering payments', () => {
    const response = proxy(adminRequest(`${VALID_ASSERTION.slice(0, -1)}X`))

    expect(response.headers.get('location')).toBe('https://example.org/login')
  })

  it('rejects an expired assertion before rendering payments', () => {
    const response = proxy(adminRequest(EXPIRED_ASSERTION))

    expect(response.headers.get('location')).toBe('https://example.org/login')
  })
})
