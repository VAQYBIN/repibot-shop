import { createHmac, timingSafeEqual } from 'node:crypto'
import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

const ADMIN_ASSERTION_COOKIE = 'repibot_admin_assertion'
const ADMIN_ASSERTION_VERSION = 1

type AdminAssertionClaims = {
  exp: number
  role: 'admin'
  v: number
}

function isAdminAssertionClaims(value: unknown): value is AdminAssertionClaims {
  if (value === null || typeof value !== 'object') return false
  const claims = value as Record<string, unknown>
  return (
    claims.v === ADMIN_ASSERTION_VERSION &&
    claims.role === 'admin' &&
    Number.isSafeInteger(claims.exp)
  )
}

function isValidAdminAssertion(assertion: string | undefined, secret: string): boolean {
  if (assertion === undefined) return false
  const [encodedClaims, encodedSignature, ...rest] = assertion.split('.')
  if (encodedClaims === undefined || encodedSignature === undefined || rest.length !== 0)
    return false

  let suppliedSignature: Buffer
  let claims: unknown
  try {
    suppliedSignature = Buffer.from(encodedSignature, 'base64url')
    claims = JSON.parse(Buffer.from(encodedClaims, 'base64url').toString('utf-8'))
  } catch {
    return false
  }

  const expectedSignature = createHmac('sha256', secret).update(encodedClaims, 'ascii').digest()
  if (suppliedSignature.length !== expectedSignature.length) return false
  if (!timingSafeEqual(suppliedSignature, expectedSignature)) return false
  if (!isAdminAssertionClaims(claims)) return false

  return claims.exp > Math.floor(Date.now() / 1000)
}

/**
 * Быстрый гейт показа платёжной админки, закрытый по умолчанию.
 *
 * `ADMIN_ASSERTION_SECRET` намеренно не NEXT_PUBLIC, и эта cookie никогда
 * не доходит до `/api`. Право на любое изменение по-прежнему выдаёт
 * `require_role(admin)` на бэкенде.
 */
export function proxy(request: NextRequest) {
  const secret = process.env.ADMIN_ASSERTION_SECRET
  const assertion = request.cookies.get(ADMIN_ASSERTION_COOKIE)?.value
  if (secret === undefined || !isValidAdminAssertion(assertion, secret)) {
    return NextResponse.redirect(new URL('/login', request.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: '/admin/payments/:path*',
}
