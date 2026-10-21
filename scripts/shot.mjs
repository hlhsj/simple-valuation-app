import { mkdirSync } from 'node:fs'
const _pw = await import(process.env.PW ?? 'file:///F:/AI/WorkBuddy/sc/node_modules/playwright-core/index.js')
const chromium = _pw.chromium ?? _pw.default?.chromium
const OUT = 'F:/AI/WorkBuddy/stock-valuation-app/shots/'
mkdirSync(OUT, { recursive: true })

const b = await chromium.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true })
const p = await b.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 })
const errs = []
p.on('pageerror', e => errs.push('pageerror: ' + e.message))
p.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()) })

await p.goto('http://127.0.0.1:8765/', { waitUntil: 'networkidle' })
await p.screenshot({ path: OUT + 'v29-01-empty.png' })

await p.fill('#q', '')
await p.type('#q', 'gzmt', { delay: 40 })
await p.waitForSelector('.sug-item', { timeout: 20000 })
console.log('联想首项:', (await p.textContent('.sug-item')).trim())
await p.screenshot({ path: OUT + 'v29-02-suggest.png' })

await p.fill('#q', '600519, 000651, 伊利股份')
await p.waitForTimeout(200)
console.log('按钮文案:', (await p.textContent('#run-text')).trim())
await p.screenshot({ path: OUT + 'v29-03-filled.png' })

await p.click('#run')
await p.waitForSelector('tbody tr', { timeout: 300000 })
await p.waitForFunction(() => !document.querySelector('#stop') || document.querySelector('#stop').classList.contains('hidden'), { timeout: 300000 })
await p.waitForTimeout(500)
await p.screenshot({ path: OUT + 'v29-04-table.png', fullPage: true })

const rowCount = await p.locator('tbody tr').count()
console.log('结果行数:', rowCount)

await p.click('tbody tr:first-child')
await p.waitForSelector('.dgrid', { timeout: 30000 })
await p.waitForTimeout(800)
await p.screenshot({ path: OUT + 'v29-05-detail.png', fullPage: true })

const t = await p.textContent('body')
const checks = {
  '无全局导航栏': !(await p.$('nav')),
  '页面标题': t.includes('股票估值实验室'),
  'v2.9 稳定版徽章': t.includes('v2.9') && t.includes('稳定版'),
  '失真风险提示': t.includes('程序化估值有失真风险'),
  '结果表': !!await p.$('tbody tr'),
  '判定已映射': /计算合理|接近合理|观望|不符合条件|淘汰|回避/.test(t),
  '估值区间标尺': !!await p.$('.ruler-band'),
  '六维进度条': !!await p.$('.dim-fill'),
  'L1 排雷': t.includes('L1 排雷'),
  '模型参数': t.includes('模型参数'),
  '免责声明': t.includes('免责声明'),
}
console.log('\n界面断言:')
for (const [k, v] of Object.entries(checks)) console.log(`  ${v ? '✓' : '✗'} ${k}`)
console.log('\n页面错误:', errs.length ? errs : '无')
await b.close()
