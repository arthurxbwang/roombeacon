import { expect, test, type Page } from '@playwright/test'

const deviceToken = 'room:omm_one:' + 'a'.repeat(43)
const sample = {
  room: { room_id: 'omm_one', name: '望岳会议室', capacity: 12, enabled: true },
  synced_at: '2026-09-15T06:20:00Z', server_time: '2026-09-15T06:20:00Z',
  valid_until: '2026-09-15T06:25:00Z', titles_available: true,
  events: [{ uid: 'one', original_time: 0, start_time: '2026-09-15T06:00:00Z', end_time: '2026-09-15T07:00:00Z', organizer: '张明', summary: '产品设计评审' },
    { uid: 'two', original_time: 0, start_time: '2026-09-15T07:30:00Z', end_time: '2026-09-15T08:30:00Z', organizer: '李婷', summary: '技术方案讨论' }],
}
async function bind(page: Page) {
  await page.addInitScript(token => { localStorage.setItem('argus_room_display', token); localStorage.setItem('argus_room_version', 'v1') }, deviceToken)
}

test('独立入口绑定后展示真实接口字段，不访问平台管理接口', async ({ page }) => {
  const requests: string[] = []
  await page.route('**/api/**', async route => {
    requests.push(new URL(route.request().url()).pathname)
    expect(route.request().headers().authorization).toBe('Bearer ' + deviceToken)
    await route.fulfill({ json: { code: 0, data: sample } })
  })
  await page.goto('/room-display.html?version=v1')
  await expect(page.getByRole('heading', { name: '绑定会议门牌' })).toBeVisible()
  await page.getByLabel('设备凭证').fill(deviceToken)
  await page.getByRole('button', { name: '绑定并显示' }).click()
  await expect(page.getByRole('heading', { name: '望岳会议室' })).toBeVisible()
  await expect(page.getByText('正在使用', { exact: true })).toBeVisible()
  await expect(page.locator('.countdown')).toContainText('40')
  expect(requests).toEqual(['/api/meeting-rooms/display'])
  await page.setViewportSize({ width: 1194, height: 834 })
  await page.screenshot({ path: '/tmp/argus-room-display-ipad.png', fullPage: true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
})

test('失联立即转未知，不能继续显示空闲', async ({ page }) => {
  await bind(page)
  await page.clock.install()
  let calls = 0
  await page.route('**/api/meeting-rooms/display', route => {
    calls++
    return calls === 1 ? route.fulfill({ json: { code: 0, data: { ...sample, events: [] } } }) : route.fulfill({ status: 502, json: { message: 'unavailable' } })
  })
  await page.goto('/room-display.html?version=v1')
  await expect(page.getByText('空闲可用', { exact: true })).toBeVisible()
  await page.clock.fastForward(16000)
  await expect(page.getByText('状态暂不可确认')).toBeVisible()
  await expect(page.getByText('空闲可用', { exact: true })).toHaveCount(0)
})

test('权限撤销清除旧会议和凭证并返回绑定页', async ({ page }) => {
  await bind(page)
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ status: 401, json: { message: 'revoked' } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.getByRole('heading', { name: '绑定会议门牌' })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('argus_room_display'))).toBeNull()
})

test('私密会议不伪造姓名和主题，手机宽度不溢出', async ({ page }) => {
  await bind(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { code: 0, data: { ...sample,
    events: [{ ...sample.events[0], organizer: null, summary: null }],
  } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.getByRole('heading', { name: '已预约会议', exact: true }).first()).toBeVisible()
  await expect(page.locator('.current')).toContainText('信息不可见')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
})

test('过期缓存不展示为正常占用或空闲', async ({ page }) => {
  await bind(page)
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { code: 0, data: { ...sample, valid_until: '2026-09-15T06:19:00Z' } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.getByText('状态暂不可确认')).toBeVisible()
  await expect(page.getByText('今日安排 · 上次同步数据')).toBeVisible()
})

test('到达结束边界自动切换为空闲，使用服务器时间而非设备时区', async ({ page }) => {
  await bind(page)
  await page.clock.install()
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { code: 0, data: { ...sample,
    server_time: '2026-09-15T06:59:59Z', valid_until: '2026-09-15T07:05:00Z',
  } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.getByText('正在使用', { exact: true })).toBeVisible()
  await page.clock.fastForward(2000)
  await expect(page.getByText('空闲可用', { exact: true })).toBeVisible()
  await expect(page.locator('.available-until')).toContainText('15:30')
})

test('跨午夜预约裁剪到滚动窗口，iPad 横屏无需滚动', async ({ page }) => {
  await bind(page)
  await page.setViewportSize({ width: 1194, height: 834 })
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { code: 0, data: { ...sample,
    server_time: '2026-09-15T00:30:00+08:00', valid_until: '2026-09-15T00:35:00+08:00',
    events: [{ ...sample.events[0], start_time: '2026-09-14T17:30:00+08:00', end_time: '2026-09-15T01:00:00+08:00' }],
  } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.getByRole('heading', { name: '望岳会议室', level: 1 })).toBeVisible()
  await expect(page.locator('.track span')).toHaveCSS('left', '0px')
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBeTruthy()
})


test('12小时时间轴随整点滚动，会议时间更醒目', async ({ page }) => {
  await bind(page)
  await page.clock.install()
  await page.setViewportSize({ width: 1194, height: 834 })
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { code: 0, data: { ...sample,
    server_time: '2026-09-15T14:59:59+08:00', valid_until: '2026-09-15T15:05:00+08:00',
  } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.locator('.ticks')).toContainText('08:00')
  await expect(page.locator('.ticks')).toContainText('20:00')
  expect(await page.locator('.countdown strong').evaluate(el => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThan(50)
  await page.clock.fastForward(2000)
  await expect(page.locator('.ticks')).toContainText('09:00')
  await expect(page.locator('.ticks')).toContainText('21:00')
})

test('测试主控筛选并切换会议室，不更换门牌绑定凭证', async ({ page }) => {
  await page.setViewportSize({ width: 1194, height: 834 })
  await page.addInitScript(() => { localStorage.setItem('argus_room_display', 'existing-binding'); localStorage.setItem('argus_room_version', 'v1') })
  await page.route('**/api/room-control/rooms', route => route.fulfill({ json: { data: [
    { room_id: 'omm_one', name: '北京一号', region: '北京', location: '北京总部', floor: '1F', capacity: 8 },
    { room_id: 'omm_two', name: '北京二号', region: '北京', location: '北京总部', floor: '2F', capacity: 12 },
    { room_id: 'omm_three', name: '上海一号', region: '上海', location: '上海园区', floor: '1F', capacity: 8 },
  ] } }))
  await page.route('**/api/room-control/preview?*', route => {
    expect(route.request().headers().authorization).toBe('Bearer test-control-credential')
    const id = new URL(route.request().url()).searchParams.get('room_id')
    return route.fulfill({ json: { data: { ...sample, ...(id === 'omm_two' ? { server_time: '2026-09-15T07:25:00Z', valid_until: '2026-09-15T07:30:00Z', events: [{ ...sample.events[1], summary: '跨团队产品设计与技术方案评审会议' }] } : {}), room: { ...sample.room, room_id: id, name: id === 'omm_one' ? '北京一号' : '北京二号' } } } })
  })
  // Mirror the standalone Nginx HTML rewrite while testing with Vite preview.
  await page.route('**/control', async route => {
    const response = await route.fetch({ url: new URL('/room-display.html', route.request().url()).href })
    await route.fulfill({ response })
  })
  await page.goto('/control/legacy')
  await page.getByLabel('测试主控凭证').fill('test-control-credential')
  await page.getByRole('button', { name: '进入主控' }).click()
  await page.getByLabel('地区 / 园区').selectOption('北京')
  await expect(page.getByRole('button', { name: '预览门牌' })).toHaveCount(2)
  await page.getByRole('button', { name: '预览门牌' }).first().click()
  await expect(page.getByRole('heading', { name: '北京一号' })).toBeVisible()
  await page.getByRole('button', { name: '☀ 日间' }).click()
  await expect(page.locator('.door')).toHaveClass(/theme-light/)
  await expect(page.locator('.current h2')).toHaveCSS('color', 'rgb(15, 23, 42)')
  await page.screenshot({ path: '/tmp/room-daylight-control.png' })
  await page.getByRole('button', { name: '☾ 夜间' }).click()
  await expect(page.locator('.door')).toHaveClass(/theme-dark/)
  await page.getByRole('button', { name: '自动', exact: true }).click()
  await expect(page.getByText('城市待配置')).toBeVisible()
  await page.getByRole('button', { name: '下一间' }).click()
  await expect(page.getByRole('heading', { name: '北京二号' })).toBeVisible()
  await expect(page.locator('.status')).toHaveText('即将开始')
  expect(await page.evaluate(() => localStorage.getItem('argus_room_display'))).toBe('existing-binding')
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBeTruthy()
  await page.screenshot({ path: '/tmp/room-control-preview.png' })
  await page.getByRole('button', { name: '返回主控', exact: false }).click()
  await expect(page.getByRole('button', { name: '预览门牌' })).toHaveCount(2)
})

test('当地日落边界自动变色，日出后恢复浅色', async ({ page }) => {
  await bind(page)
  await page.clock.install()
  let serverTime = '2026-09-15T10:19:59Z'
  const daylight = { city: '北京', timezone: 'Asia/Shanghai', valid_until: '2026-09-18T00:00:00Z', windows: [
    { start: '2026-09-15T00:00:00Z', end: '2026-09-15T10:20:00Z' },
    { start: '2026-09-16T00:00:00Z', end: '2026-09-16T10:20:00Z' },
  ] }
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: { ...sample, server_time: serverTime, daylight, events: [] } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.locator('.door')).toHaveClass(/theme-light/)
  await page.clock.fastForward(2000)
  await expect(page.locator('.door')).toHaveClass(/theme-dark/)
  serverTime = '2026-09-16T00:00:00Z'
  await page.clock.fastForward(15000)
  await expect(page.locator('.door')).toHaveClass(/theme-light/)
})

test('海外当地日期和夏令时当天日程正确', async ({ page }) => {
  await bind(page)
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: { ...sample,
    server_time: '2026-11-02T04:30:00Z', valid_until: '2026-11-02T04:35:00Z',
    daylight: { city: '多伦多', timezone: 'America/Toronto', windows: [], valid_until: '2026-11-04T00:00:00Z' },
    events: [{ ...sample.events[0], start_time: '2026-11-02T04:00:00Z', end_time: '2026-11-02T04:50:00Z' }],
  } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.locator('.clock strong')).toHaveText('23:30')
  await expect(page.locator('.clock p')).toContainText('11月1日')
  await expect(page.locator('.status')).toHaveText('正在使用')
  await expect(page.locator('.meeting-time')).toHaveText('23:00 — 23:50')
})

test('即将开始突出下一场，过去会议折叠且保留预约占位', async ({ page }) => {
  await bind(page)
  await page.setViewportSize({ width: 1194, height: 834 })
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: { ...sample,
    server_time: '2026-09-15T07:25:00Z', valid_until: '2026-09-15T07:30:00Z',
  } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.locator('.status')).toHaveText('即将开始')
  await expect(page.locator('.countdown')).toHaveText('5分钟')
  await expect(page.locator('.agenda article').first()).toContainText('技术方案讨论')
  await expect(page.locator('.current')).toContainText('组织者 · 李婷')
  await expect(page.getByText('预约入口待接入')).toBeVisible()
  await expect(page.locator('.status')).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await page.getByText('已结束 · 1 场').click()
  await expect(page.locator('.history')).toContainText('产品设计评审')
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBeTruthy()
})

test('无后续预约填充空态，不把有历史会议的日子称为全天空闲', async ({ page }) => {
  await bind(page)
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: { ...sample,
    server_time: '2026-09-15T09:00:00Z', valid_until: '2026-09-15T09:05:00Z',
  } } }))
  await page.goto('/room-display.html?version=v1')
  await expect(page.locator('.agenda-empty')).toContainText('今日会议已结束')
  await expect(page.locator('.room-fact')).toContainText('12')
  await expect(page.getByText('欢迎使用')).toHaveCount(0)
  await expect(page.locator('.status')).toHaveText('空闲可用')
})
