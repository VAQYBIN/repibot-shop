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
    'ratelimit:register:ip:*',
  ])
}

function runSql(sql: string, variables: Record<string, string> = {}): void {
  const command = [
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
  runComposeCommand(command, sql)
}

function runComposeCommand(args: string[], input?: string): void {
  const command = [
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
