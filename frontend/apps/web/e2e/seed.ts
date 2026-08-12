/** Детерминированные данные для отдельного compose-стека Playwright. */

import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

const ROOT = resolve(__dirname, '../../../..')
const PROJECT = 'repibot-e2e'
const ENV_FILE = 'frontend/apps/web/e2e/stack.env'
const FILES = ['compose.yml', 'frontend/apps/web/e2e/compose.e2e.yml']

export const SEEDED_PLAN_CODE = 'month'
export const PANEL_URL = process.env.E2E_PANEL_URL ?? 'http://localhost:3001'

export interface SeededSubscription {
  email: string
  panelId: number
  panelShortUuid: string
  subscriptionUrl: string
}

const PLANS_SQL = `
INSERT INTO plans (
  code, name, description, duration_days, price_rub, price_stars,
  traffic_limit_bytes, traffic_reset_strategy, hwid_device_limit,
  internal_squad_uuids, is_trial, is_active, is_visible, sort_order
) VALUES
  (
    'month', '{"ru":"Месяц","en":"Month"}'::jsonb,
    '{"ru":"Доступ на 30 дней","en":"30 days of access"}'::jsonb,
    30, 299.00, 300, 107374182400, 'MONTH', 3,
    ARRAY[]::uuid[], false, true, true, 10
  ),
  (
    'trial', '{"ru":"Пробный","en":"Trial"}'::jsonb,
    '{"ru":"Три дня бесплатно","en":"Three days free"}'::jsonb,
    3, 0.00, 0, 1073741824, 'NO_RESET', 1,
    ARRAY[]::uuid[], true, true, false, 100
  )
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  duration_days = EXCLUDED.duration_days,
  price_rub = EXCLUDED.price_rub,
  price_stars = EXCLUDED.price_stars,
  traffic_limit_bytes = EXCLUDED.traffic_limit_bytes,
  traffic_reset_strategy = EXCLUDED.traffic_reset_strategy,
  hwid_device_limit = EXCLUDED.hwid_device_limit,
  internal_squad_uuids = EXCLUDED.internal_squad_uuids,
  is_trial = EXCLUDED.is_trial,
  is_active = EXCLUDED.is_active,
  is_visible = EXCLUDED.is_visible,
  sort_order = EXCLUDED.sort_order,
  updated_at = now();
`

const SUBSCRIPTION_SQL = `
BEGIN;

SELECT 1 / CASE WHEN count(*) = 1 THEN 1 ELSE 0 END
FROM users
WHERE email = :'email';

UPDATE users SET
  remnawave_id = :'panel_id'::bigint,
  remnawave_short_uuid = :'panel_short_uuid',
  remnawave_subscription_url = :'subscription_url',
  updated_at = now()
WHERE email = :'email';

INSERT INTO subscriptions (
  user_id, plan_id, status, started_at, expires_at,
  auto_renew_enabled, source
)
SELECT
  users.id, plans.id, 'active', now(), TIMESTAMPTZ '2099-01-01 00:00:00+00',
  false, 'admin'
FROM users
JOIN plans ON plans.code = 'month'
WHERE users.email = :'email'
ON CONFLICT (user_id) DO UPDATE SET
  plan_id = EXCLUDED.plan_id,
  status = EXCLUDED.status,
  started_at = EXCLUDED.started_at,
  expires_at = EXCLUDED.expires_at,
  auto_renew_enabled = EXCLUDED.auto_renew_enabled,
  source = EXCLUDED.source,
  updated_at = now();

COMMIT;
`

/**
 * Заполнить общие тарифы и, если передан пользователь панели, его подписку.
 *
 * SQL приходит psql через stdin, а значения — через его переменные. Shell не
 * участвует, поэтому адрес почты или ссылка не превращаются в часть команды.
 */
export function seed(subscription?: SeededSubscription): void {
  runSql(PLANS_SQL)
  if (subscription === undefined) return
  if (!Number.isSafeInteger(subscription.panelId) || subscription.panelId <= 0) {
    throw new Error('panelId для посева должен быть положительным целым числом')
  }
  runSql(SUBSCRIPTION_SQL, {
    email: subscription.email,
    panel_id: String(subscription.panelId),
    panel_short_uuid: subscription.panelShortUuid,
    subscription_url: subscription.subscriptionUrl,
  })
}

/**
 * Начать группу сценариев регистрации с чистым тестовым лимитом.
 *
 * Все браузеры отдельного compose-проекта приходят в nginx с одного адреса,
 * поэтому семь независимых E2E-регистраций исчерпывают продуктовый лимит в
 * пять попыток. Очищается только этот ключ и только внутри `repibot-e2e`:
 * сессии, письма, кэши и стек разработчика не затрагиваются.
 */
export function resetRegistrationRateLimit(): void {
  resetRateLimitKeys('ratelimit:register:ip:*')
}

/**
 * То же для создания заказов: пять в минуту с адреса.
 *
 * Полный прогон заводит заказы в нескольких файлах подряд, и все они приходят
 * с одного адреса — к платёжным сценариям лимит уже исчерпан соседями. Без
 * сброса тест падает не на своём предмете, а на защите от кликера формы.
 */
export function resetOrderRateLimit(): void {
  resetRateLimitKeys('ratelimit:payment-create:ip:*')
}

function resetRateLimitKeys(pattern: string): void {
  const script = [
    "local keys = redis.call('keys', ARGV[1])",
    "for _, key in ipairs(keys) do redis.call('del', key) end",
    'return #keys',
  ].join('; ')
  runComposeCommand([
    'exec',
    '--no-TTY',
    'valkey',
    'valkey-cli',
    '--raw',
    'EVAL',
    script,
    '0',
    pattern,
  ])
}

/**
 * Выдать роль исключительно пользователю из отдельного e2e-compose проекта.
 *
 * Это позволяет открыть server-gated экран админа без общего `ADMIN_TELEGRAM_IDS`
 * и не может обратиться к базе разработческого или production-стека.
 */
export function grantE2eAdmin(email: string): void {
  runSql("UPDATE users SET role = 'admin', updated_at = now() WHERE email = :'email'", { email })
  const userId = querySql("SELECT id FROM users WHERE email = :'email'", { email })
  if (!/^\d+$/.test(userId)) {
    throw new Error('не удалось найти E2E-пользователя для обновления роли')
  }
  // Браузер зарегистрировался обычным пользователем, и после этой намеренно
  // изолированной смены роли refresh не вправе переиспользовать старый кэш.
  runComposeCommand(['exec', '--no-TTY', 'valkey', 'valkey-cli', 'DEL', `principal:${userId}`])
}

/**
 * Заводит человека с готовым номером Телеграма — для сквозного обхода MiniApp.
 *
 * Подписанный initData называет номер, которого до этого вызова в базе нет:
 * без строки в `users` вход в MiniApp автосоздал бы пустого пользователя без
 * email, и это никак не хуже с точки зрения самого входа, но так — предсказуемо
 * тем же приёмом, каким `grantE2eAdmin` выше меняет роль уже существующей строке.
 */
export function seedTelegramUser(telegramId: number, username: string): void {
  assertToken(username, 'telegram username')
  if (!Number.isSafeInteger(telegramId) || telegramId <= 0) {
    throw new Error('telegramId для посева MiniApp должен быть положительным целым числом')
  }
  runSql(
    `INSERT INTO users (telegram_id, telegram_username, email_verified_at, referral_code, language)
     VALUES (:'telegram_id', :'username', now(), substring(md5(:'username') FROM 1 FOR 16), 'ru')
     ON CONFLICT (telegram_id) DO UPDATE SET telegram_username = EXCLUDED.telegram_username`,
    { telegram_id: String(telegramId), username },
  )
}

/**
 * Публикует соглашение, на которое ссылается подвал.
 *
 * Без него `/legal/terms` отдаёт 404, и сквозной обход публичных экранов падает
 * на пустой базе — по настоящей причине, но не там, где её станут искать.
 */
export function seedLegalDocuments(): void {
  runSql(
    `INSERT INTO legal_documents (slug, locale, title, content, version, published_at)
     VALUES (
       'terms', 'ru', 'Пользовательское соглашение',
       E'## Общие положения\\n\\nТекст соглашения для сквозного обхода.\\n',
       1, now()
     )
     ON CONFLICT (slug, locale, version) DO UPDATE SET
       title = EXCLUDED.title,
       content = EXCLUDED.content,
       published_at = EXCLUDED.published_at,
       withdrawn_at = NULL,
       updated_at = now()`,
  )
}

/** Кладёт истёкший промокод в ту же схему Postgres, что и оформление. */
export function seedExpiredPromo(code: string): void {
  assertToken(code, 'promo code')
  runSql(
    `INSERT INTO promo_codes (
       code, percent_off, bonus_days, max_uses, per_user_limit, is_active, starts_at, expires_at
     ) VALUES (
       :'code', 20, 0, NULL, NULL, true,
       now() - interval '2 days', now() - interval '1 minute'
     )
     ON CONFLICT (code) DO UPDATE SET
       percent_off = EXCLUDED.percent_off,
       bonus_days = EXCLUDED.bonus_days,
       is_active = EXCLUDED.is_active,
       starts_at = EXCLUDED.starts_at,
       expires_at = EXCLUDED.expires_at,
       updated_at = now()`,
    { code },
  )
}

/** Кладёт оплаченный подарочный заказ и ваучер для настоящего погашения. */
export function seedGiftVoucher(email: string, code: string): void {
  assertToken(code, 'gift code')
  runSql(
    `WITH gift_order AS (
       INSERT INTO orders (
         user_id, purpose, plan_id, plan_code_snapshot, plan_name_snapshot,
         duration_days_snapshot, price_rub_snapshot, price_stars_snapshot,
         gross_rub, discount_rub, amount_due_rub, promo_code_id, client_key,
         expires_at, status, fulfilled_at
       )
       SELECT users.id, 'gift', plans.id, plans.code, plans.name,
              plans.duration_days, plans.price_rub, plans.price_stars,
              plans.price_rub, 0.00, plans.price_rub, NULL,
              concat('e2e-gift-', :'code'), now() + interval '1 day', 'fulfilled', now()
       FROM users
       JOIN plans ON plans.code = 'month'
       WHERE users.email = :'email'
       RETURNING id, user_id
     )
     INSERT INTO gift_vouchers (order_id, code, purchased_by_user_id, expires_at)
     SELECT id, :'code', user_id, now() + interval '365 days'
     FROM gift_order`,
    { email, code },
  )
}

/** Привязывает зарегистрированного пользователя к заранее известному рефереру. */
export function seedReferrerFor(refereeEmail: string, referrerEmail: string): void {
  runSql(
    `INSERT INTO users (email, email_verified_at, referral_code)
     VALUES (
       :'referrer_email', now(), substring(md5(:'referrer_email') FROM 1 FOR 16)
     )
     ON CONFLICT (email) DO UPDATE SET email_verified_at = EXCLUDED.email_verified_at;

     UPDATE users AS referee
     SET referred_by_id = referrer.id, updated_at = now()
     FROM users AS referrer
     WHERE referee.email = :'referee_email' AND referrer.email = :'referrer_email'`,
    { referee_email: refereeEmail, referrer_email: referrerEmail },
  )
}

/**
 * Создаёт два уже проверенных платежа. Финализация идёт в образе API
 * с выбранным реферальным режимом, а не правкой работающего веб-процесса.
 */
export function seedReferralOrders(email: string, marker: string): void {
  assertToken(marker, 'referral marker')
  runSql(
    `WITH paid_orders AS (
       INSERT INTO orders (
         user_id, purpose, plan_id, plan_code_snapshot, plan_name_snapshot,
         duration_days_snapshot, price_rub_snapshot, price_stars_snapshot,
         gross_rub, discount_rub, amount_due_rub, promo_code_id, client_key,
         expires_at, status
       )
       SELECT users.id, 'purchase', plans.id, plans.code, plans.name,
              plans.duration_days, plans.price_rub, plans.price_stars,
              plans.price_rub, 0.00, plans.price_rub, NULL, keys.client_key,
              now() + interval '1 day', 'pending'
       FROM users
       JOIN plans ON plans.code = 'month'
       CROSS JOIN (
         VALUES
           (concat('e2e-referral-', :'marker', '-one')),
           (concat('e2e-referral-', :'marker', '-two'))
       ) AS keys(client_key)
       WHERE users.email = :'email'
       RETURNING id, client_key
     )
     INSERT INTO payment_attempts (
       order_id, provider, attempt_no, provider_key, provider_payment_id,
       status, verified_payload, verified_at
     )
     SELECT id, 'yookassa', 1,
            concat('e2e-referral-key-', client_key),
            concat('e2e-referral-payment-', client_key),
            'succeeded',
            jsonb_build_object(
              'amount', '299.00',
              'currency', 'RUB',
              'status', 'succeeded',
              'payment_method_id', 'e2e-referral-method'
            ),
            now()
     FROM paid_orders`,
    { email, marker },
  )
}

/** Финализирует обе посеянные попытки внутри изолированного образа API. */
export function runReferralFinalization(email: string, mode: 'first' | 'every'): string {
  return runApiPython(
    `import asyncio
import os

from sqlalchemy import select

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.db.models import Order, PaymentAttempt, User
from repibot_core.services.payments import PaymentService
from repibot_core.settings import get_settings


async def main() -> None:
    settings = get_settings().model_copy(
        update={"referral_reward_mode": os.environ["E2E_REFERRAL_MODE"]}
    )
    engine = create_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            attempts = list(
                (
                    await session.scalars(
                        select(PaymentAttempt.id)
                        .join(Order, Order.id == PaymentAttempt.order_id)
                        .join(User, User.id == Order.user_id)
                        .where(
                            User.email == os.environ["E2E_REFERRAL_EMAIL"],
                            Order.client_key.like("e2e-referral-%"),
                        )
                        .order_by(PaymentAttempt.id)
                    )
                ).all()
            )
            await session.commit()
            if len(attempts) != 2:
                raise RuntimeError(f"expected two referral attempts, got {len(attempts)}")
            service = PaymentService(session, settings)
            for attempt_id in attempts:
                await service.finalize_success(attempt_id)
            print(f"finalized={len(attempts)} mode={settings.referral_reward_mode}")
    finally:
        await engine.dispose()


asyncio.run(main())`,
    { E2E_REFERRAL_EMAIL: email, E2E_REFERRAL_MODE: mode },
  )
}

/**
 * Кладёт действующую карту и фиксированный срок для планировщика.
 *
 * Карта живёт отдельной строкой `saved_payment_methods`: именно её берёт
 * автопродление, а не `payment_method_id` из исторических попыток. Посев без
 * этой строки оставил бы подписку без способа списания, и цикл не начался бы.
 */
export function seedAutoRenewalSubscription(email: string, methodId: string, marker: string): void {
  assertToken(methodId, 'saved payment method')
  assertToken(marker, 'renewal marker')
  runSql(
    `UPDATE users
     SET telegram_id = (900000000 + (abs(hashtext(:'marker')) % 1000000000))::bigint,
         updated_at = now()
     WHERE email = :'email';

     INSERT INTO saved_payment_methods (user_id, provider, provider_method_id, title)
     SELECT users.id, 'yookassa', :'method_id', 'Bank card *4444'
     FROM users
     WHERE users.email = :'email'
     ON CONFLICT DO NOTHING;

     INSERT INTO subscriptions (
       user_id, plan_id, status, started_at, expires_at, auto_renew_enabled,
       source, entitlement_price_rub, entitlement_duration_days
     )
     SELECT users.id, plans.id, 'active', TIMESTAMPTZ '2029-12-01 00:00:00+00',
            TIMESTAMPTZ '2030-01-01 00:00:00+00', true,
            'purchase', plans.price_rub, plans.duration_days
     FROM users
     JOIN plans ON plans.code = 'month'
     WHERE users.email = :'email'
     ON CONFLICT (user_id) DO UPDATE SET
       plan_id = EXCLUDED.plan_id,
       status = EXCLUDED.status,
       started_at = EXCLUDED.started_at,
       expires_at = EXCLUDED.expires_at,
       auto_renew_enabled = EXCLUDED.auto_renew_enabled,
       source = EXCLUDED.source,
       entitlement_price_rub = EXCLUDED.entitlement_price_rub,
       entitlement_duration_days = EXCLUDED.entitlement_duration_days,
       updated_at = now();

     WITH initial_order AS (
       INSERT INTO orders (
         user_id, purpose, plan_id, plan_code_snapshot, plan_name_snapshot,
         duration_days_snapshot, price_rub_snapshot, price_stars_snapshot,
         gross_rub, discount_rub, amount_due_rub, promo_code_id, client_key,
         expires_at, status, fulfilled_at
       )
       SELECT users.id, 'purchase', plans.id, plans.code, plans.name,
              plans.duration_days, plans.price_rub, plans.price_stars,
              plans.price_rub, 0.00, plans.price_rub, NULL,
              concat('e2e-renew-seed-', :'marker'), now() + interval '1 day', 'fulfilled', now()
       FROM users
       JOIN plans ON plans.code = 'month'
       WHERE users.email = :'email'
       RETURNING id
     )
     INSERT INTO payment_attempts (
       order_id, provider, attempt_no, provider_key, provider_payment_id,
       status, verified_payload, verified_at
     )
     SELECT id, 'yookassa', 1,
            concat('e2e-renew-initial-key-', :'marker'),
            concat('e2e-renew-initial-payment-', :'marker'),
            'succeeded',
            jsonb_build_object(
              'amount', '299.00',
              'currency', 'RUB',
              'status', 'succeeded',
              'payment_method_id', :'method_id'
            ),
            now()
     FROM initial_order`,
    { email, method_id: methodId, marker },
  )
}

/** Запускает боевой AutoRenewalService в заданный момент UTC. */
export function runAutoRenewalAt(now: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/.test(now)) {
    throw new Error('E2E auto-renew time must be an explicit UTC ISO timestamp')
  }
  return runApiPython(
    `import asyncio
import os
from datetime import datetime

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.integrations.yookassa.client import create_yookassa_client
from repibot_core.services.payment_notifications import AutoRenewalService
from repibot_core.settings import get_settings


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    client = create_yookassa_client()
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            calls = await AutoRenewalService(session, client, settings).run(
                now=datetime.fromisoformat(os.environ["E2E_RENEWAL_NOW"])
            )
            print(f"calls={calls}")
    finally:
        await client.aclose()
        await engine.dispose()


asyncio.run(main())`,
    { E2E_RENEWAL_NOW: now },
  )
}

/** Повторяет событие в одной транзакции: строки по каналам обязаны остаться уникальными. */
export function runNotificationDedup(orderId: number, kind: string): string {
  if (!Number.isSafeInteger(orderId) || orderId <= 0) {
    throw new Error('E2E notification order id must be a positive integer')
  }
  assertToken(kind, 'notification kind')
  return runApiPython(
    `import asyncio
import os

from repibot_core.db.engine import create_engine, create_session_factory
from repibot_core.services.payment_notifications import NotificationService
from repibot_core.settings import get_settings


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            async with session.begin():
                service = NotificationService(session)
                first = await service.enqueue_payment_event(
                    int(os.environ["E2E_NOTIFICATION_ORDER_ID"]),
                    os.environ["E2E_NOTIFICATION_KIND"],
                )
                second = await service.enqueue_payment_event(
                    int(os.environ["E2E_NOTIFICATION_ORDER_ID"]),
                    os.environ["E2E_NOTIFICATION_KIND"],
                )
                print(f"staged={first},{second}")
    finally:
        await engine.dispose()


asyncio.run(main())`,
    {
      E2E_NOTIFICATION_ORDER_ID: String(orderId),
      E2E_NOTIFICATION_KIND: kind,
    },
  )
}

function assertToken(value: string, label: string): void {
  if (!/^[A-Za-z0-9_-]{1,96}$/.test(value)) {
    throw new Error(
      `${label} may contain only ASCII letters, digits, underscores, and hyphens in E2E seed data`,
    )
  }
}

function runSql(sql: string, variables: Record<string, string> = {}): void {
  runComposeCommand(psqlCommand(variables), sql)
}

/** Выполняет запрос только в одноразовой базе E2E. */
export function querySql(sql: string, variables: Record<string, string> = {}): string {
  return runComposeOutput(
    [...psqlCommand(variables), '--tuples-only', '--no-align', '--field-separator=|'],
    sql,
  ).trim()
}

function psqlCommand(variables: Record<string, string>): string[] {
  return [
    'exec',
    '--no-TTY',
    'postgres',
    'psql',
    '--no-psqlrc',
    '--quiet',
    '--username',
    'repibot',
    '--dbname',
    'repibot',
    '--set',
    'ON_ERROR_STOP=1',
    ...Object.entries(variables).flatMap(([key, value]) => ['--set', `${key}=${value}`]),
  ]
}

function composeCommand(args: string[]): string[] {
  return [
    'compose',
    '--project-name',
    PROJECT,
    '--env-file',
    ENV_FILE,
    ...FILES.flatMap((file) => ['--file', file]),
    '--profile',
    'dev',
    ...args,
  ]
}

function runComposeCommand(args: string[], input?: string): void {
  const command = composeCommand(args)
  try {
    execFileSync('docker', command, {
      cwd: ROOT,
      input,
      stdio: ['pipe', 'inherit', 'inherit'],
    })
  } catch (error) {
    const code = (error as { code?: string }).code
    if (code === 'ENOENT') {
      throw new Error('посеву сквозных тестов нужен Docker: команда docker не найдена')
    }
    throw new Error('команда сквозного compose-стека завершилась с ошибкой')
  }
}

function runComposeOutput(args: string[], input?: string): string {
  const command = composeCommand(args)
  try {
    return execFileSync('docker', command, {
      cwd: ROOT,
      input,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'inherit'],
    })
  } catch (error) {
    const code = (error as { code?: string }).code
    if (code === 'ENOENT') {
      throw new Error('посеву сквозных тестов нужен Docker: команда docker не найдена')
    }
    throw new Error('команда сквозного compose-стека завершилась с ошибкой')
  }
}

function runApiPython(script: string, environment: Record<string, string>): string {
  const env = Object.entries(environment).flatMap(([key, value]) => ['--env', `${key}=${value}`])
  return runComposeOutput(['exec', '--no-TTY', ...env, 'api', 'python', '-'], script)
}
