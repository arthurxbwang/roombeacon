/** Run only against the debug APK + loopback fixture; never a production room. */
import { _android } from '../../frontend/node_modules/playwright-core/index.mjs'
import { execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync, renameSync } from 'node:fs'
import { resolve } from 'node:path'
import assert from 'node:assert/strict'

const serial = process.env.ROOMBEACON_TEST_SERIAL
const adbPath = process.env.ROOMBEACON_ADB || 'adb'
const output = resolve(process.env.ROOMBEACON_TEST_OUTPUT || '.local-tools/device-test')
const stateFile = resolve(process.env.ROOMBEACON_FIXTURE_STATE || '.local-tools/fixture-state.json')
if (!serial) throw new Error('Set ROOMBEACON_TEST_SERIAL explicitly')
mkdirSync(output, { recursive: true })
const app = 'com.roombeacon.shell.debug'
const adb = (...args) => execFileSync(adbPath, ['-s', serial, ...args], { timeout: 20000, encoding: 'utf8' }).trim()
const state = changes => {
  writeFileSync(`${stateFile}.next`, JSON.stringify({ release: 'fixture-a', skip_binding: true, ...changes }))
  renameSync(`${stateFile}.next`, stateFile)
}
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
const results = []
let browser
let page

async function connect() {
  const devices = await _android.devices({ omitDriverInstall: true })
  browser = devices.find(device => device.serial() === serial)
  assert.ok(browser, 'Requested Android device not found')
  const webview = await browser.webView({ pkg: app }, { timeout: 20000 })
  page = await webview.page()
  assert.ok(page && page.url().startsWith('http://127.0.0.1:8765/'), 'Only the loopback fixture may be tested')
}
async function check(name, action) {
  if (!new RegExp(process.env.ROOMBEACON_TEST_FILTER || '.*').test(name)) return
  await action()
  results.push({ name, passed: true, time: new Date().toISOString() })
  writeFileSync(resolve(output, 'results.json'), JSON.stringify(results, null, 2))
  console.log(`PASS ${name}`)
}
async function contains(text) { await page.getByText(text, { exact: false }).first().waitFor({ timeout: 35000 }) }

try {
  await connect()
  state({})
  await check('V3 renders on physical WebView 106', async () => {
    await contains('测试会议室 · 非真实日程')
    const metrics = await page.evaluate(() => ({
      userAgent: navigator.userAgent, width: innerWidth, height: innerHeight,
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
      viewportFallback: !CSS.supports('height', '100dvh'),
      doorHeight: document.querySelector('.door').getBoundingClientRect().height,
    }))
    assert.equal(metrics.horizontalOverflow, false)
    assert.ok(Math.abs(metrics.doorHeight - metrics.height) < 2)
    writeFileSync(resolve(output, 'webview.json'), JSON.stringify(metrics, null, 2))
    await page.screenshot({ path: resolve(output, 'v3-fixture.png') })
  })
  await check('503 becomes unknown and recovers', async () => {
    state({ api_status: 503 })
    await contains('状态暂不可确认')
    state({})
    await contains('使用中')
  })
  await check('Network transport loss becomes unknown and reconnects', async () => {
    adb('reverse', '--remove', 'tcp:8765')
    try { await contains('状态暂不可确认') }
    finally { adb('reverse', 'tcp:8765', 'tcp:8765') }
    await contains('使用中')
  })
  await check('Process restart preserves origin and binding', async () => {
    await browser.close()
    adb('shell', 'am', 'force-stop', app)
    adb('shell', 'am', 'start', '-n', `${app}/com.roombeacon.shell.MainActivity`)
    await delay(4000)
    await connect()
    await contains('测试会议室 · 非真实日程')
  })
  await check('401 removes binding and schedule', async () => {
    state({ api_status: 401 })
    await contains('凭证已失效，请重新绑定')
    assert.equal(await page.evaluate(() => localStorage.getItem('argus_room_display')), null)
    assert.equal(await page.locator('.room-identity').count(), 0)
    state({ skip_binding: false })
    await page.reload()
    await contains('测试会议室 · 非真实日程')
    state({})
  })
  await check('Server-only release and rollback, accelerated browser clock', async () => {
    await page.clock.install()
    await page.reload()
    await contains('使用中')
    for (const release of ['fixture-b', 'fixture-c', 'fixture-a']) {
      state({ release })
      await page.evaluate(() => sessionStorage.removeItem('roombeacon_last_reload'))
      await page.clock.runFor(301000)
      await page.waitForFunction(value => document.querySelector('meta[name="roombeacon-release"]')?.content === value, release)
      await contains('测试会议室 · 非真实日程')
    }
  })
  await check('Cold start with HTTP 503 shows native fallback then recovers', async () => {
    await browser.close()
    state({ page_status: 503 })
    adb('shell', 'am', 'force-stop', app)
    adb('shell', 'am', 'start', '-n', `${app}/com.roombeacon.shell.MainActivity`)
    let fallback = false
    for (let attempt = 0; attempt < 6 && !fallback; attempt++) {
      await delay(1000)
      adb('shell', 'uiautomator', 'dump', '/data/local/tmp/roombeacon-ui.xml')
      fallback = adb('shell', 'cat', '/data/local/tmp/roombeacon-ui.xml').includes('当前会议状态不可确认')
    }
    assert.ok(fallback, 'Native fallback must replace the failed business page')
    const pid = adb('shell', 'pidof', app)
    const logs = adb('shell', 'logcat', '-d', '-s', 'RoomBeacon:I')
    assert.ok(!logs.split('\n').some(line => line.includes(` ${pid} `) && line.includes('page_ready')),
      'HTTP failure must not be cleared by late page callbacks')
    state({})
    await delay(10000)
    await connect()
    await contains('测试会议室 · 非真实日程')
  })
  await check('Renderer crash recovers without losing binding', async () => {
    const prior = adb('shell', 'logcat', '-d', '-s', 'RoomBeacon:I').split('显示进程已退出').length
    const pid = adb('shell', 'pidof', app)
    const cdp = await page.context().newCDPSession(page)
    // A crash is expected to reject/disconnect the command itself.
    const crash = cdp.send('Page.crash').catch(() => {})
    await Promise.race([crash, delay(3000)])
    await browser.close()
    await delay(5000)
    await connect()
    await contains('测试会议室 · 非真实日程')
    assert.equal(adb('shell', 'pidof', app), pid, 'APK process should survive renderer death')
    assert.ok(adb('shell', 'logcat', '-d', '-s', 'RoomBeacon:I').split('显示进程已退出').length > prior,
      'Renderer termination callback must actually have occurred')
  })
} finally {
  state({})
  if (browser) await browser.close()
}
