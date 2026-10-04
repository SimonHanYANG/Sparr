/**
 * Authed UI self-review shots (CLAUDE.md): logs in via the API, injects JWT
 * into localStorage, then screenshots each path at mobile/tablet/desktop.
 * Usage: node scripts/shot-authed.mjs <user> <pass> <path:prefix> [...more path:prefix]
 *   e.g. node scripts/shot-authed.mjs shot_user 'ShotPass1!23' '/applications:apps' '/applications/1:room'
 */
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const [user, pass, ...specs] = process.argv.slice(2)
const API = 'http://127.0.0.1:8010'
const WEB = 'http://localhost:5173'
const outDir = '/tmp/sparr-shots'
mkdirSync(outDir, { recursive: true })

const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1280, height: 800 },
]

const loginResp = await fetch(`${API}/api/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: user, password: pass }),
})
if (!loginResp.ok) throw new Error(`login failed: ${loginResp.status}`)
const { access, refresh } = await loginResp.json()

const browser = await chromium.launch()
for (const spec of specs) {
  const [path, prefix] = spec.split(':')
  for (const vp of VIEWPORTS) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } })
    await page.goto(WEB, { waitUntil: 'networkidle' })
    await page.evaluate(
      ([a, r]) => {
        localStorage.setItem('sparr_access', a)
        localStorage.setItem('sparr_refresh', r)
      },
      [access, refresh],
    )
    await page.goto(WEB + path, { waitUntil: 'networkidle' })
    await page.waitForTimeout(600)
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
    await page.screenshot({ path: `${outDir}/${prefix}-${vp.name}.png`, fullPage: true })
    await page.close()
  }
}
await browser.close()
