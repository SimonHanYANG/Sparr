/**
 * UI self-review helper (CLAUDE.md): screenshots at mobile/tablet/desktop with
 * Playwright's own Chromium (reliable viewport rendering), animations disabled,
 * plus an overflow check.
 * Usage: node scripts/screenshot.mjs <url> <out-prefix>
 */
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const url = process.argv[2] ?? 'http://localhost:5173/'
const prefix = process.argv[3] ?? 'page'
const outDir = '/tmp/sparr-shots'
mkdirSync(outDir, { recursive: true })

const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1280, height: 800 },
]

const browser = await chromium.launch()

for (const vp of VIEWPORTS) {
  const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } })
  await page.goto(url, { waitUntil: 'networkidle' })
  // neutralize animations so screenshots show the settled state
  await page.addStyleTag({
    content:
      '*,*::before,*::after{animation:none!important;transition:none!important;opacity:1!important;transform:none!important}',
  })
  const diag = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    overflowing: document.documentElement.scrollWidth > window.innerWidth + 1,
  }))
  console.log(`${prefix}@${vp.name} (${vp.width}px):`, JSON.stringify(diag))
  await page.screenshot({ path: `${outDir}/${prefix}-${vp.name}.png` })
  await page.close()
}

await browser.close()
