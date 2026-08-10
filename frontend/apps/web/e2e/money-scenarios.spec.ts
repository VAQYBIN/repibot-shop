import { expect, type Page, test } from '@playwright/test'

import { waitForLink } from './mailpit'
import {
  querySql,
  resetRegistrationRateLimit,
  runAutoRenewalAt,
  runNotificationDedup,
  runReferralFinalization,
  seedAutoRenewalSubscription,
  seedExpiredPromo,
  seedGiftVoucher,
  seedReferralOrders,
  seedReferrerFor,
} from './seed'
import { MAILPIT_URL, WEB_URL } from './stack'

const PASSWORD = 'надёжный пароль для денежных сценариев'
const VERIFY_LINK = /https?:\/\/\S+\/verify-email\S+/
const FAKE_YOOKASSA_URL = process.env.E2E_YOOKASSA_URL ?? 'http://127.0.0.1:3002'

let sequence = 0

test.beforeEach(() => resetRegistrationRateLimit())

function unique(prefix: string): string {
  sequence += 1
  return `${prefix}-${Date.now()}-${sequence}`
}

function uniqueEmail(prefix: string): string {
  return `${unique(prefix)}@example.com`
}

async function registerAndSignIn(page: Page, email: string): Promise<void> {
  await page.goto('/register')
  await page.getByLabel('Почта', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Зарегистрироваться' }).click()
  const link = await waitForLink(MAILPIT_URL, email, VERIFY_LINK)
  await page.goto(link)
  await expect(page).toHaveURL(/\/account/)
}

async function createCardOrder(page: Page): Promise<string> {
  await page.goto('/account/payments')
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/me/orders') && response.request().method() === 'POST',
    ),
    page.getByRole('button', { name: 'Оплатить картой' }).click(),
  ])
  const latest = await page.request.get(`${FAKE_YOOKASSA_URL}/__e2e/payments/latest`)
  expect(latest.ok()).toBe(true)
  return (await latest.json()).id as string
}

/**
 * Выбирает за плательщика галочку «запомнить карту» на следующей оплате.
 *
 * Настоящую галочку показывает форма провайдера, которой на стенде нет:
 * заглушка запоминает решение заранее и отдаёт его в ответе о платеже.
 */
async function setSavedCardChoice(page: Page, saved: boolean): Promise<void> {
  const chosen = await page.request.post(`${FAKE_YOOKASSA_URL}/__e2e/cards/save-next`, {
    data: { saved },
  })
  expect(chosen.ok()).toBe(true)
}

async function setFakePaymentStatus(
  page: Page,
  paymentId: string,
  status: 'succeeded' | 'canceled',
): Promise<void> {
  const updated = await page.request.post(
    `${FAKE_YOOKASSA_URL}/__e2e/payments/${paymentId}/status`,
    { data: { status } },
  )
  expect(updated.ok()).toBe(true)
}

async function confirmCardPayment(page: Page, paymentId: string): Promise<void> {
  await setFakePaymentStatus(page, paymentId, 'succeeded')
  const webhook = await page.request.post(`${WEB_URL}/webhook/yookassa`, {
    data: { object: { id: paymentId, status: 'untrusted' } },
  })
  expect(webhook.status()).toBe(204)
}

function rows(sql: string, variables: Record<string, string> = {}): string[][] {
  const output = querySql(sql, variables)
  return output === '' ? [] : output.split('\n').map((line) => line.split('|'))
}

/** Все строки карт пользователя: название и признак «действует». */
function savedCards(email: string): string[][] {
  return rows(
    `SELECT saved.title, (saved.revoked_at IS NULL)::text
     FROM saved_payment_methods saved
     JOIN users ON users.id = saved.user_id
     WHERE users.email = :'email'
     ORDER BY saved.id`,
    { email },
  )
}

/** Настройка автопродления в базе — она же источник состояния переключателя. */
function autoRenewFlag(email: string): string {
  return querySql(
    `SELECT subscriptions.auto_renew_enabled::text
     FROM subscriptions
     JOIN users ON users.id = subscriptions.user_id
     WHERE users.email = :'email'`,
    { email },
  )
}

test('просроченный промокод отклоняется API и не создаёт заказ в изолированном стеке', async ({
  page,
}) => {
  const email = uniqueEmail('expired-promo')
  const code = unique('EXPIRED').toUpperCase()
  await registerAndSignIn(page, email)
  seedExpiredPromo(code)

  await page.goto('/account/payments')
  await page.getByLabel('Промокод', { exact: true }).fill(code)
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/me/orders') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Оплатить картой' }).click()
  const response = await responsePromise

  expect(response.status()).toBe(409)
  await expect(response.json()).resolves.toMatchObject({ error: { code: 'promo_unavailable' } })
  await expect(page.getByText('Промокод недоступен', { exact: true })).toBeVisible()
  expect(
    querySql(
      "SELECT count(*) FROM orders JOIN users ON users.id = orders.user_id WHERE users.email = :'email'",
      { email },
    ),
  ).toBe('0')
})

test('подарочный ваучер применяется ровно один раз через UI и API', async ({ page }) => {
  const email = uniqueEmail('gift-once')
  const code = unique('gift')
  await registerAndSignIn(page, email)
  seedGiftVoucher(email, code)

  await page.goto('/account/payments')
  await page.getByLabel('Код ваучера', { exact: true }).fill(code)
  const firstResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/me/gifts/redeem') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Активировать ваучер' }).click()
  const firstResponse = await firstResponsePromise

  expect(firstResponse.status()).toBe(200)
  await expect(firstResponse.json()).resolves.toMatchObject({
    subscription: { plan_code: 'month' },
  })
  expect(
    querySql(
      "SELECT count(*) FROM gift_vouchers WHERE code = :'code' AND redeemed_at IS NOT NULL",
      {
        code,
      },
    ),
  ).toBe('1')

  const secondResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/me/gifts/redeem') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Активировать ваучер' }).click()
  const secondResponse = await secondResponsePromise

  expect(secondResponse.status()).toBe(409)
  await expect(secondResponse.json()).resolves.toMatchObject({
    error: { code: 'gift_unavailable' },
  })
  await expect(
    page.getByText('Ваучер уже использован или недоступен', { exact: true }),
  ).toBeVisible()
  expect(querySql("SELECT count(*) FROM gift_vouchers WHERE code = :'code'", { code })).toBe('1')
})

test('режим first начисляет рефереру только за первый подтверждённый заказ', async ({ page }) => {
  const email = uniqueEmail('referral-first')
  await registerAndSignIn(page, email)
  seedReferrerFor(email, uniqueEmail('referrer-first'))

  await confirmCardPayment(page, await createCardOrder(page))
  await confirmCardPayment(page, await createCardOrder(page))

  expect(
    querySql(
      `SELECT count(*)
       FROM referral_rewards reward
       JOIN users referee ON referee.id = reward.referee_user_id
       WHERE referee.email = :'email'`,
      { email },
    ),
  ).toBe('1')
  expect(
    querySql(
      `SELECT string_agg(reward.days::text, ',' ORDER BY reward.origin_order_id)
       FROM referral_rewards reward
       JOIN users referee ON referee.id = reward.referee_user_id
       WHERE referee.email = :'email'`,
      { email },
    ),
  ).toBe('3')
})

test('режим every начисляет за каждый оплаченный заказ', async ({ page }) => {
  const email = uniqueEmail('referral-every')
  await registerAndSignIn(page, email)
  seedReferrerFor(email, uniqueEmail('referrer-every'))
  seedReferralOrders(email, unique('every'))
  runReferralFinalization(email, 'every')

  expect(
    querySql(
      `SELECT count(*)
       FROM referral_rewards reward
       JOIN users referee ON referee.id = reward.referee_user_id
       WHERE referee.email = :'email'`,
      { email },
    ),
  ).toBe('2')
  expect(
    querySql(
      `SELECT string_agg(reward.days::text, ',' ORDER BY reward.origin_order_id)
       FROM referral_rewards reward
       JOIN users referee ON referee.id = reward.referee_user_id
       WHERE referee.email = :'email'`,
      { email },
    ),
  ).toBe('3,3')
  await page.goto('/account/subscription')
  await expect(page.getByText('Месяц', { exact: true })).toBeVisible()
})

test('автопродление идёт циклами -24/-18/-6, держит сохранённую карту и не дублирует каналы', async ({
  page,
}) => {
  const email = uniqueEmail('auto-renew')
  const marker = unique('renew')
  const methodId = `saved-${marker}`
  await registerAndSignIn(page, email)
  seedAutoRenewalSubscription(email, methodId, marker)

  runAutoRenewalAt('2029-12-31T00:00:00+00:00')
  const firstPayment = querySql(
    `SELECT attempt.provider_payment_id
     FROM payment_attempts attempt
     JOIN orders ON orders.id = attempt.order_id
     JOIN users ON users.id = orders.user_id
     WHERE users.email = :'email' AND orders.client_key LIKE 'auto-renew:%' AND attempt.attempt_no = 1`,
    { email },
  )
  expect(firstPayment).toMatch(/^fake-payment-\d+$/)

  await setFakePaymentStatus(page, firstPayment, 'canceled')
  runAutoRenewalAt('2029-12-31T06:00:00+00:00')
  const secondPayment = querySql(
    `SELECT attempt.provider_payment_id
     FROM payment_attempts attempt
     JOIN orders ON orders.id = attempt.order_id
     JOIN users ON users.id = orders.user_id
     WHERE users.email = :'email' AND orders.client_key LIKE 'auto-renew:%' AND attempt.attempt_no = 2`,
    { email },
  )
  expect(secondPayment).toMatch(/^fake-payment-\d+$/)

  await setFakePaymentStatus(page, secondPayment, 'canceled')
  runAutoRenewalAt('2029-12-31T18:00:00+00:00')
  const thirdPayment = querySql(
    `SELECT attempt.provider_payment_id
     FROM payment_attempts attempt
     JOIN orders ON orders.id = attempt.order_id
     JOIN users ON users.id = orders.user_id
     WHERE users.email = :'email' AND orders.client_key LIKE 'auto-renew:%' AND attempt.attempt_no = 3`,
    { email },
  )
  expect(thirdPayment).toMatch(/^fake-payment-\d+$/)

  await setFakePaymentStatus(page, thirdPayment, 'canceled')
  runAutoRenewalAt('2029-12-31T18:00:00+00:00')

  const attempts = rows(
    `SELECT attempt.attempt_no::text, attempt.status::text, attempt.provider_payment_id,
            attempt.verified_payload ->> 'payment_method_id'
     FROM payment_attempts attempt
     JOIN orders ON orders.id = attempt.order_id
     JOIN users ON users.id = orders.user_id
     WHERE users.email = :'email' AND orders.client_key LIKE 'auto-renew:%'
     ORDER BY attempt.attempt_no`,
    { email },
  )
  expect(attempts.map(([number]) => number)).toEqual(['1', '2', '3'])
  expect(attempts.map(([, status]) => status)).toEqual(['failed', 'failed', 'failed'])
  expect(new Set(attempts.map(([, , paymentId]) => paymentId)).size).toBe(3)
  expect(attempts.map(([, , , savedMethod]) => savedMethod)).toEqual([methodId, methodId, methodId])

  const firstOrderId = Number(
    querySql(
      `SELECT orders.id
       FROM orders
       JOIN users ON users.id = orders.user_id
       WHERE users.email = :'email' AND orders.client_key LIKE 'auto-renew:%:1'`,
      { email },
    ),
  )
  expect(runNotificationDedup(firstOrderId, 'auto_renew_failed_1')).toContain('staged=0,0')
  expect(
    rows(
      `SELECT delivery.kind, delivery.channel, count(*)::text
       FROM notification_deliveries delivery
       JOIN orders ON orders.id = delivery.order_id
       JOIN users ON users.id = orders.user_id
       WHERE users.email = :'email' AND delivery.kind LIKE 'auto_renew_failed_%'
       GROUP BY delivery.kind, delivery.channel
       ORDER BY delivery.kind, delivery.channel`,
      { email },
    ),
  ).toEqual([
    ['auto_renew_failed_1', 'email', '1'],
    ['auto_renew_failed_1', 'telegram', '1'],
    ['auto_renew_failed_2', 'email', '1'],
    ['auto_renew_failed_2', 'telegram', '1'],
    ['auto_renew_failed_3', 'email', '1'],
    ['auto_renew_failed_3', 'telegram', '1'],
  ])

  await page.goto('/account/payments')
  await expect(page.getByRole('switch', { name: 'Автопродление' })).not.toBeChecked()
})

test('галочка «запомнить карту» включает автоплатёж, оплата без неё ничего не меняет, отвязка выключает', async ({
  page,
}) => {
  const email = uniqueEmail('saved-card')
  await registerAndSignIn(page, email)

  // До первой оплаты карты нет, а без подписки переключателю нечего показывать.
  await page.goto('/account/payments')
  await expect(page.getByText('Карта не привязана', { exact: true })).toBeVisible()
  await expect(page.getByRole('switch', { name: 'Автопродление' })).toHaveCount(0)
  expect(savedCards(email)).toEqual([])

  // Плательщик отметил галочку на форме провайдера.
  await setSavedCardChoice(page, true)
  await confirmCardPayment(page, await createCardOrder(page))

  await page.goto('/account/payments')
  await expect(page.getByText('Bank card *4444', { exact: true })).toBeVisible()
  const toggle = page.getByRole('switch', { name: 'Автопродление' })
  await expect(toggle).toBeEnabled()
  await expect(toggle).toBeChecked()
  expect(savedCards(email)).toEqual([['Bank card *4444', 'true']])
  expect(autoRenewFlag(email)).toBe('true')

  // Вторая оплата без галочки: она означает «эту карту не запоминать», а не
  // «забыть прежнюю», поэтому ни строки карты, ни настройки не прибавится.
  await setSavedCardChoice(page, false)
  await confirmCardPayment(page, await createCardOrder(page))

  await page.goto('/account/payments')
  await expect(page.getByText('Bank card *4444', { exact: true })).toBeVisible()
  await expect(page.getByRole('switch', { name: 'Автопродление' })).toBeChecked()
  expect(savedCards(email)).toEqual([['Bank card *4444', 'true']])
  expect(autoRenewFlag(email)).toBe('true')

  // Отвязка идёт через подтверждение: кнопка в окне называется так же, как та,
  // что его открыла, поэтому вторая ищется внутри самого окна.
  await page.getByRole('button', { name: 'Отвязать карту' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Отвязать карту' }).click()

  await expect(page.getByText('Карта не привязана', { exact: true })).toBeVisible()
  const disabled = page.getByRole('switch', { name: 'Автопродление' })
  await expect(disabled).toBeDisabled()
  await expect(disabled).not.toBeChecked()
  expect(savedCards(email)).toEqual([['Bank card *4444', 'false']])
  expect(autoRenewFlag(email)).toBe('false')
})
