import { mkdirSync } from 'node:fs'

const _pw = await import(
  process.env.PW ?? 'file:///F:/AI/WorkBuddy/sc/node_modules/playwright-core/index.js')
const chromium = _pw.chromium ?? _pw.default?.chromium

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.env.BASE ?? 'http://127.0.0.1:8765'
const OUT = new URL('../shots/', import.meta.url).pathname.replace(/^\//, '')
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const page = await browser.newPage({ viewport: { width: 1240, height: 980 }, deviceScaleFactor: 2 })
const errs = []
page.on('pageerror', e => errs.push('pageerror: ' + e.message))
page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()) })

await page.goto(BASE, { waitUntil: 'networkidle' })
await page.screenshot({ path: OUT + '01-empty.png' })

await page.fill('#q', 'gzmt')
await page.waitForSelector('.sug.on .sug-item', { timeout: 20000 })
const sug = await page.textContent('.sug-item')
console.log('联想首项:', sug.trim().replace(/\s+/g, ' '))
await page.screenshot({ path: OUT + '02-suggest.png' })

await page.click('.sug-item')
await page.waitForSelector('.card.head', { timeout: 180000 })
await page.waitForTimeout(600)
await page.screenshot({ path: OUT + '03-result.png', fullPage: true })

const t = await page.textContent('body')
const checks = {
  '头部名称': !!await page.$('.head h1'),
  '风险徽章': !!await page.$('.badge'),
  '六维雷达': !!await page.$('svg polygon'),
  '合理区间': t.includes('合理区间'),
  '安全边际': t.includes('理论安全边际'),
  '期望收益': t.includes('期望年化收益'),
  '排雷区块': t.includes('一、排雷'),
  '六维区块': t.includes('二、六维评分'),
  '估值区块': t.includes('三、估值与决策'),
}
console.log('\n界面断言:')
for (const [k, v] of Object.entries(checks)) console.log(`  ${v ? '✓' : '✗'} ${k}`)

console.log('\n页面错误:', errs.length ? errs : '无')
await browser.close()
