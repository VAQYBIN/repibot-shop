/**
 * Растеризация бренд-набора: SVG → PNG через Chromium.
 *
 * Браузер здесь не прихоть: это единственный движок, которым мы и так
 * пользуемся, и он рисует SVG ровно так же, как увидит пользователь.
 *
 * Результат коммитится и под verify_generated не попадает — байты рендера
 * зависят от версии Chromium, и проверка ругалась бы после каждого его
 * обновления.
 *
 * Браузер ставится командой из CONTRIBUTING.md:
 *   pnpm --filter @repibot/web exec playwright install chromium
 */
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const LOGO = resolve(ROOT, 'docs/design/logo')
const RASTER = resolve(LOGO, 'raster')
const WEB = resolve(ROOT, 'frontend/apps/web/public')

const JOBS = [
  { svg: 'favicon.svg', out: 'favicon-16.png', width: 16, height: 16 },
  { svg: 'favicon.svg', out: 'favicon-32.png', width: 32, height: 32 },
  { svg: 'badge.svg', out: 'icon-192.png', width: 192, height: 192 },
  { svg: 'badge.svg', out: 'icon-512.png', width: 512, height: 512 },
  { svg: 'avatar.svg', out: 'avatar-512.png', width: 512, height: 512 },
  { svg: 'og-image.svg', out: 'og-image.png', width: 1200, height: 630 },
]

// og-image остаётся в бренд-наборе: страниц, которыми делятся, пока нет,
// а класть в public файл без потребителя незачем.
const COPIES = ['favicon-16.png', 'favicon-32.png', 'icon-192.png', 'icon-512.png']

mkdirSync(RASTER, { recursive: true })

const browser = await chromium.launch()
try {
  for (const job of JOBS) {
    const svg = readFileSync(resolve(LOGO, job.svg))
    const source = `data:image/svg+xml;base64,${svg.toString('base64')}`
    const page = await browser.newPage({
      viewport: { width: job.width, height: job.height },
      deviceScaleFactor: 1,
    })
    await page.setContent(
      '<style>html,body{margin:0;padding:0}img{display:block;width:100%;height:100%}</style>' +
        `<img src="${source}" alt="">`,
    )
    await page.screenshot({ path: resolve(RASTER, job.out), omitBackground: true })
    await page.close()
    console.log(`${job.out} ${job.width}×${job.height}`)
  }
} finally {
  await browser.close()
}

for (const name of COPIES) {
  copyFileSync(resolve(RASTER, name), resolve(WEB, name))
}
console.log(`Скопировано в веб: ${COPIES.length}`)
