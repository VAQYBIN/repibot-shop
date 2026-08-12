/**
 * Пересоздаёт nginx со смонтированной пробной главной.
 *
 * Том монтируется при создании контейнера: подменить каталог у работающего
 * nginx нельзя, поэтому его пересоздают. После прогона контур возвращается
 * в исходное состояние — иначе следующий сквозной обход увидит вместо
 * главной пробную страницу и не объяснит почему.
 */

import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

const ROOT = resolve(__dirname, '../../../..')
const PROJECT = 'repibot-e2e'
const ENV_FILE = 'frontend/apps/web/e2e/stack.env'
const FILES = ['compose.yml', 'frontend/apps/web/e2e/compose.e2e.yml']
const PROBE_DIR = 'frontend/apps/web/e2e/landing-probe'

function compose(landingDir: string, ...args: string[]): void {
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
  execFileSync('docker', command, {
    cwd: ROOT,
    stdio: 'inherit',
    // Значение из окружения перебивает и --env-file, и умолчание в compose.yml:
    // каталог выбирается на время одного прогона и нигде не записывается.
    env: { ...process.env, LANDING_DIR: landingDir },
  })
}

export function mountProbeLanding(): void {
  compose(PROBE_DIR, 'up', '-d', '--force-recreate', 'nginx')
}

export function restoreDefaultLanding(): void {
  compose('./landing', 'up', '-d', '--force-recreate', 'nginx')
}
