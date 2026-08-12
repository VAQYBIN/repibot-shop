/**
 * Стек для сквозных тестов: поднимается перед прогоном, живёт в отдельном
 * проекте compose и слушает свои порты.
 *
 * Тесты идут через настоящий nginx к настоящему API, а не к `next start`:
 * кабинет держится на refresh-cookie и относительных путях `/api`, и проверять
 * это без обратного прокси нечем.
 */

import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

import { seed, seedLegalDocuments } from './seed'

const ROOT = resolve(__dirname, '../../../..')
const PROJECT = 'repibot-e2e'
const ENV_FILE = 'frontend/apps/web/e2e/stack.env'
const FILES = ['compose.yml', 'frontend/apps/web/e2e/compose.e2e.yml']

/** Адреса заданы в stack.env: ссылки в письмах должны вести туда же, куда ходит браузер. */
export const WEB_URL = process.env.E2E_WEB_URL ?? 'http://localhost:8081'
export const MAILPIT_URL = process.env.E2E_MAILPIT_URL ?? 'http://localhost:8026'

function compose(...args: string[]): void {
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
    execFileSync('docker', command, { cwd: ROOT, stdio: 'inherit' })
  } catch (error) {
    const code = (error as { code?: string }).code
    if (code === 'ENOENT') {
      throw new Error('сквозным тестам нужен Docker: команда docker не найдена')
    }
    throw new Error(`docker compose ${args.join(' ')} завершился с ошибкой`)
  }
}

async function waitFor(url: string, what: string, timeoutMs = 120_000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  let lastError: unknown = null

  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
      lastError = `ответ ${response.status}`
    } catch (error) {
      lastError = error
    }
    await new Promise((done) => setTimeout(done, 1000))
  }

  throw new Error(`${what} не поднялся за ${timeoutMs} мс: ${String(lastError)}`)
}

export default async function globalSetup(): Promise<void> {
  // Стек пересоздаётся с нуля вместе с томами. В Valkey живут счётчики
  // попыток, а регистраций разрешено пять в час на адрес: второй прогон подряд
  // на прежних данных упёрся бы в лимит, а не в поведение продукта.
  compose('down', '--volumes', '--remove-orphans')
  // --build обязателен: тесты должны проверять текущий код, а не образ,
  // собранный неизвестно когда.
  compose('up', '--detach', '--build', '--wait', '--wait-timeout', '300')

  await waitFor(`${WEB_URL}/health`, 'API')
  await waitFor(`${WEB_URL}/login`, 'веб-приложение')
  await waitFor(`${MAILPIT_URL}/api/v1/info`, 'Mailpit')
  seed()
  seedLegalDocuments()
}
