import { expect, test, type Page } from '@playwright/test'

const event = { uid: 'current', original_time: 0, summary: '产品设计评审', organizer: '张明', start_time: '2026-09-16T14:00:00+08:00', end_time: '2026-09-16T15:00:00+08:00' }
const data = { room: { room_id: 'omm_one', name: '207', capacity: 9, enabled: true }, server_time: '2026-09-16T14:20:00+08:00', synced_at: '2026-09-16T14:20:00+08:00', valid_until: '2026-09-16T14:25:00+08:00', titles_available: true, events: [
  { ...event, uid: 'past', summary: '已结束会议', start_time: '2026-09-16T11:00:00+08:00', end_time: '2026-09-16T12:00:00+08:00' }, event,
  { ...event, uid: 'next', summary: '下一场会议', start_time: '2026-09-16T16:00:00+08:00', end_time: '2026-09-16T17:00:00+08:00' },
  { ...event, uid: 'later', summary: '更晚的会议', start_time: '2026-09-16T18:00:00+08:00', end_time: '2026-09-16T19:00:00+08:00' },
] }
async function control(page: Page, schedule = data) {
  await page.addInitScript(() => { sessionStorage.setItem('argus_room_control', 'fixture'); if (!localStorage.getItem('argus_room_version')) localStorage.setItem('argus_room_version', 'v2') })
  await page.route('**/control', async route => route.fulfill({ response: await route.fetch({ url: new URL('/room-display.html', route.request().url()).href }) }))
  await page.route('**/api/room-control/rooms', route => route.fulfill({ json: { data: [{ ...data.room, region: '北京', location: '北京', floor: '2F' }] } }))
  await page.route('**/api/room-control/preview?*', route => route.fulfill({ json: { data: schedule } }))
  await page.goto('/control/legacy')
  await page.getByRole('button', { name: '预览门牌' }).click()
  await expect(page.locator('.door')).toHaveClass(/v2/)
}

test('V2 仅保留本场下一场，时间轴独立配色，V1可切换并持久保存', async ({ page }) => {
  await control(page)
  await expect(page.locator('.agenda article')).toHaveCount(2)
  await expect(page.locator('.agenda')).not.toContainText('更晚的会议')
  await expect(page.locator('.history')).toHaveCount(0)
  await expect(page.locator('.track span')).toHaveCount(4)
  await expect(page.locator('.track span').nth(1)).toHaveCSS('background-color', 'rgb(239, 68, 68)')
  await expect(page.locator('.track span').first()).toHaveCSS('background-color', 'rgb(100, 116, 139)')
  await page.getByRole('button', { name: '☀ 日间' }).click()
  await expect(page.locator('.track')).toHaveCSS('background-color', 'rgb(209, 250, 229)')
  await page.getByLabel('门牌版本').selectOption('v1')
  await expect(page.locator('.agenda article')).toHaveCount(3)
  await expect(page.locator('.history')).toBeVisible()
  await page.reload()
  await page.getByRole('button', { name: '预览门牌' }).click()
  await expect(page.getByLabel('门牌版本')).toHaveValue('v1')
  await page.getByLabel('门牌版本').selectOption('v2')
  await page.getByRole('button', { name: '全屏', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出全屏' })).toBeVisible()
  expect(await page.evaluate(() => !!document.fullscreenElement)).toBeTruthy()
  await page.getByRole('button', { name: '退出全屏' }).click()
  await expect(page.getByRole('button', { name: '全屏', exact: true })).toBeVisible()
})

for (const [width, height] of [[1920, 1080], [1280, 800], [1024, 600], [1194, 834], [800, 1280], [390, 844]]) {
  for (const state of ['busy', 'soon', 'free']) test(`V2 ${state} 屏幕 ${width}×${height} 内容可达且不横向溢出`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await control(page, state === 'soon' ? { ...data, server_time: '2026-09-16T13:55:00+08:00' } : state === 'free' ? { ...data, events: [] } : data)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    const layout = await page.locator('.door').evaluate(el => {
      const main = el.querySelector('.current')!.getBoundingClientRect()
      const info = el.querySelector('.primary-info')!.getBoundingClientRect()
      return { horizontal: el.scrollWidth <= el.clientWidth, mainBottom: main.bottom, infoBottom: info.bottom }
    })
    expect(layout.horizontal).toBeTruthy()
    expect(layout.infoBottom).toBeLessThanOrEqual(layout.mainBottom + 1)
    await page.locator('footer').scrollIntoViewIfNeeded()
    await expect(page.locator('footer')).toBeInViewport()
    await page.screenshot({ path: `/tmp/v2-${state}-${width}-${height}.png`, fullPage: true })
  })
}

test('V2 失效日程不把未知空档标成可约绿色，URL可固定 V1', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: { ...data, valid_until: '2026-09-16T14:00:00+08:00' } } }))
  await page.goto('/room-display.html?version=v2')
  await expect(page.locator('.track')).toHaveClass(/unknown/)
  await expect(page.locator('.status')).toHaveText('状态暂不可确认')
  await page.goto('/room-display.html?version=v1')
  await expect(page.locator('.door')).not.toHaveClass(/v2/)
})

test('全屏不受支持时显示可操作提示', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(Element.prototype, 'requestFullscreen', { value: undefined }))
  await control(page)
  await page.getByRole('button', { name: '全屏', exact: true }).click()
  await expect(page.getByText('此浏览器不支持网页全屏，请使用浏览器全屏或添加到主屏幕')).toBeVisible()
})

test('网络失败继续显示历史会议并标记时间，恢复后自动替换', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
  await page.clock.install()
  let calls = 0
  await page.route('**/api/meeting-rooms/display', route => {
    calls++
    if (calls === 2) return route.fulfill({ status: 502, json: { message: 'temporary failure' } })
    return route.fulfill({ json: { data: calls >= 3 ? { ...data, events: [] } : data } })
  })
  await page.goto('/room-display.html?version=v2')
  await expect(page.locator('.current')).toContainText('产品设计评审')
  await page.clock.fastForward(16000)
  await expect(page.locator('.history-warning')).toContainText('最后同步')
  await expect(page.locator('.current')).toContainText('产品设计评审')
  await expect(page.locator('.organizer')).toContainText('张明')
  await expect(page.locator('.status')).toHaveText('状态暂不可确认')
  await expect(page.locator('.track')).toHaveClass(/unknown/)
  await page.clock.fastForward(15000)
  await expect(page.locator('.history-warning')).toHaveCount(0)
  await expect(page.locator('.status')).toHaveText('空闲可用')
  await expect(page.locator('.current')).not.toContainText('产品设计评审')
})

test('V3 签到卡片随版本切换，取消预约占位，未配置时隐藏', async ({ page }) => {
  const schedule = { ...data, events: [], checkin_qr: 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciLz4=' }
  await control(page, schedule)
  await expect(page.locator('.booking-guide')).toBeVisible()
  await page.getByLabel('门牌版本').selectOption('v3')
  await expect(page.locator('.booking-guide')).toHaveCount(0)
  await expect(page.locator('.current .checkin-card')).toContainText('飞书扫码签到')
  await expect(page.locator('.agenda .checkin-card')).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('argus_room_version'))).toBe('v3')
  await page.getByLabel('门牌版本').selectOption('v2')
  await expect(page.locator('.checkin-card')).toHaveCount(0)
  await page.getByLabel('门牌版本').selectOption('v3')
  await page.route('**/api/room-control/preview?*', route => route.fulfill({ json: { data } }))
  await page.getByRole('button', { name: '← 返回主控' }).click()
  await page.getByRole('button', { name: '预览门牌' }).click()
  await expect(page.locator('.current')).toContainText('产品设计评审')
  await expect(page.locator('.checkin-card')).toHaveCount(0)
})

test('V3 1280×800 签到布局上滑不滚动整页或移走状态边框', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
  const checkin_qr = 'data:image/svg+xml;base64,' + Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"/>').toString('base64')
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: { ...data, checkin_qr } } }))
  await page.goto('/room-display.html?version=v3')
  await expect(page.locator('.checkin-qr')).toBeVisible()
  const door = page.locator('.door')
  expect(await door.evaluate(el => el.scrollHeight - el.clientHeight)).toBeLessThanOrEqual(1)
  await page.mouse.move(640, 780)
  await page.mouse.wheel(0, 400)
  await expect.poll(() => door.evaluate(el => el.scrollTop)).toBe(0)
  await expect(page.locator('.door-header')).toBeInViewport({ ratio: 1 })
  await expect(page.locator('footer')).toBeInViewport({ ratio: 1 })
})

test('V3 轮询自动新增、更换和移除签到码，无需刷新页面', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
  await page.clock.install()
  const qr = (color: string) => 'data:image/svg+xml;base64,' + Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="${color}"/></svg>`).toString('base64')
  let currentQr: string | null = null
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: { ...data, checkin_qr: currentQr } } }))
  await page.goto('/room-display.html?version=v3')
  await expect(page.locator('.room-identity h1')).toHaveText('207')
  await expect(page.locator('.checkin-card')).toHaveCount(0)
  let navigations = 0
  page.on('framenavigated', frame => { if (frame === page.mainFrame()) navigations++ })
  for (const color of ['black', 'blue']) {
    currentQr = qr(color)
    await page.clock.fastForward(16000)
    await expect(page.locator('.checkin-qr')).toHaveAttribute('src', currentQr)
    await expect(page.locator('.checkin-card')).toBeVisible()
  }
  currentQr = null
  await page.clock.fastForward(16000)
  await expect(page.locator('.checkin-card')).toHaveCount(0)
  expect(navigations).toBe(0)
  expect(await page.evaluate(() => localStorage.getItem('argus_room_display'))).toBe('fixture')
})

test('V3 后续会议跨日期取最近两场，不包含本场，状态外框跟随占用', async ({ page }) => {
  const schedule = { ...data, events: [data.events[1]!, { ...event, uid: 'tomorrow', summary: '明日评审', start_time: '2026-09-17T09:00:00+08:00', end_time: '2026-09-17T10:00:00+08:00' }, data.events[2]!, { ...event, uid: 'third', summary: '不应显示', start_time: '2026-09-17T11:00:00+08:00', end_time: '2026-09-17T12:00:00+08:00' }] }
  await control(page, schedule)
  await page.getByLabel('门牌版本').selectOption('v3')
  await expect(page.locator('.agenda-header')).toContainText('后续会议')
  await expect(page.locator('.agenda article')).toHaveCount(2)
  await expect(page.locator('.agenda')).toContainText('下一场会议')
  await expect(page.locator('.agenda')).toContainText('明日评审')
  await expect(page.locator('.agenda')).not.toContainText('产品设计评审')
  await expect(page.locator('.agenda')).not.toContainText('不应显示')
  await expect(page.locator('.current .status')).toHaveText('使用中')
  expect(await page.locator('.door').evaluate(el => getComputedStyle(el, '::after').borderTopColor)).toBe('rgb(239, 68, 68)')
})
