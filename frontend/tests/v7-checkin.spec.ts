import { expect, test, type Page } from '@playwright/test'
import { fixture } from './configuration.fixture'

async function scene(page: Page, options: { time?: string; phase?: string; height?: number; dark?: boolean; mode?: string; paused?: boolean; verified?: boolean; managed?: boolean; control?: boolean; owner?: string; deadline?: string; releaseEnabled?: boolean; buffer?: number } = {}) {
  const time = options.time || '2026-09-28T06:10:00Z'
  await page.clock.install({ time: new Date(Date.parse(time) - 1000) })
  await page.clock.pauseAt(new Date(time))
  await page.setViewportSize({ width: 1280, height: options.height || 720 })
  await page.addInitScript(() => {
    localStorage.setItem('argus_room_display', 'fixture')
    localStorage.setItem('argus_room_usage_v5:omm_fixture', 'usage:omm_fixture:' + 'a'.repeat(43))
  })
  const occurrence = { uid: 'fixture', original_time: 0, start_time: '2026-09-28T06:15:00Z', end_time: '2026-09-28T06:30:00Z' }
  const state = { room_id: 'omm_fixture', enabled: true, release_enabled: options.releaseEnabled ?? true, paused: options.paused ?? false, target_id: 'a'.repeat(64), can_confirm: true, can_end: false,
    policy: { owner: options.owner || 'v5', mode: options.mode || 'auto', early_minutes: 5, grace_minutes: 5, release_delay_seconds: options.buffer ?? 60, native_policy_cleared: true, release_verified: true, revision: 'fixture' },
    record: { id: 'a'.repeat(64), state: options.phase || 'pending', verified: options.verified ?? true, deadline: options.deadline || '2026-09-28T06:20:00Z', occurrence,
      ...(options.phase === 'waiting' ? { release_at: options.buffer === 0 ? '2026-09-28T06:20:00Z' : '2026-09-28T06:21:00Z' } : {}) } }
  const currentTime = () => page.evaluate(() => Date.now())
  await page.route('**/api/meeting-rooms/display', async route => route.fulfill({ json: { data: {
    room: { room_id: 'omm_fixture', name: 'V7 模拟会议室', capacity: 4, enabled: true },
    server_time: new Date(await currentTime()).toISOString(), synced_at: time, valid_until: '2026-09-28T07:00:00Z', usage_owner: options.owner || 'v5', titles_available: true,
    display_preferences: { theme_mode: options.dark ? 'dark' : 'light', language: 'zh-CN', display_version: options.managed ? 'v7' : 'v6', usage_control: options.control !== false },
    events: [{ ...occurrence, summary: '模拟预约 · 非真实会议', organizer: '测试数据' }, { ...occurrence, uid: 'next', start_time: '2026-09-28T06:30:00Z', end_time: '2026-09-28T06:45:00Z', summary: '下一场模拟预约', organizer: '测试数据' }],
    checkin_qr: 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="white"/></svg>'),
  } } }))
  for (const path of ['usage', 'usage/heartbeat']) await page.route(`**/api/meeting-rooms/${path}`, async route => {
    const now = await currentTime()
    await route.fulfill({ json: { data: { ...state, server_time: new Date(now).toISOString(), valid_until: new Date(now + 30000).toISOString() } } })
  })
  await page.goto('/room-display.html?version=' + (options.managed ? 'v6&managed=1' : 'v7'))
  return state
}

for (const height of [720, 800]) for (const dark of [false, true]) test(`V7 品牌签到适配 1280×${height} ${dark ? '夜间' : '日间'}`, async ({ page }, info) => {
  await scene(page, { height, dark })
  await expect(page.locator('.door.v7')).toBeVisible()
  await expect(page.getByLabel('距离会议开始', { exact: true })).toHaveText('05:00')
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toBeEnabled()
  await expect(page.locator('.v7-brand img')).toBeVisible()
  // Brand inversion must never leak onto the full display or button.
  expect(await page.locator('.door').evaluate(e => getComputedStyle(e).filter)).toBe('none')
  expect(await page.locator('.v7-button').evaluate(e => getComputedStyle(e).color)).toBe('rgb(255, 255, 255)')
  await expect(page.getByText('提前签到，保留本场会议')).toHaveCount(0)
  await expect(page.getByText('签到截止', { exact: false })).toHaveCount(0)
  await page.clock.fastForward(1000)
  await expect(page.getByLabel('距离会议开始', { exact: true })).toHaveText('04:59')
  const layout = await page.locator('.door').evaluate(door => {
    const panels = ['.v7-checkin', '.usage-body', '.primary-body', '.agenda-body', '.timeline']
    return { overflow: door.scrollHeight > door.clientHeight, panels: panels.map(s => { const e = door.querySelector(s)!; const r = e.getBoundingClientRect(); return { selector: s, clipped: e.scrollHeight > e.clientHeight + 1, outside: r.bottom > innerHeight || r.top < 0 } }) }
  })
  expect(layout.overflow).toBe(false)
  expect(layout.panels.every(p => !p.clipped && !p.outside)).toBe(true)
  await page.screenshot({ path: info.outputPath('v7.png') })
})

test('会前跨越会议开始，重新显示会后五分钟', async ({ page }) => {
  await scene(page, { time: '2026-09-28T06:14:59Z' })
  await expect(page.getByLabel('距离会议开始', { exact: true })).toHaveText('00:01')
  await page.clock.fastForward(1000)
  await expect(page.getByLabel('未签到将释放 · 剩余', { exact: true })).toHaveText('05:00')
  await expect(page.locator('.v7-checkin')).toHaveAttribute('data-phase', 'after')
})

test('以服务器期限为准，不伪造五分钟；截止后等待核验', async ({ page }) => {
  await scene(page, { time: '2026-09-28T06:19:59Z', deadline: '2026-09-28T06:22:00Z' })
  await expect(page.getByLabel('未签到将释放 · 剩余', { exact: true })).toHaveText('02:01')
  await page.clock.fastForward(122000)
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
  await expect(page.getByText('正在同步释放状态', { exact: true })).toBeVisible()
  await expect(page.getByText('本次预约已释放', { exact: true })).toHaveCount(0)
})

test('补签到使用服务器 release_at，成功后清除倒计时', async ({ page }) => {
  const state = await scene(page, { time: '2026-09-28T06:20:15Z', phase: 'waiting' })
  await expect(page.getByLabel('释放前补签到 · 剩余', { exact: true })).toHaveText('00:45')
  let calls = 0
  await page.route('**/api/meeting-rooms/usage/confirm', async route => {
    calls++
    state.record.state = 'confirmed'; state.can_confirm = false
    await route.fulfill({ json: { data: { ...state, valid_until: '2026-09-28T06:21:00Z' } } })
  })
  await page.getByRole('button', { name: '立即签到', exact: true }).click()
  await expect(page.getByText('已签到', { exact: true })).toBeVisible()
  await expect(page.getByRole('timer')).toHaveCount(0)
  expect(calls).toBe(1)
})

for (const options of [{ releaseEnabled: false }, { paused: true }, { verified: false }, { mode: 'observe' }, { phase: 'blocked' }]) test(`保护状态不承诺自动释放 ${JSON.stringify(options)}`, async ({ page }) => {
  await scene(page, { time: '2026-09-28T06:16:00Z', ...options })
  await expect(page.getByLabel('未签到将释放 · 剩余', { exact: true })).toHaveCount(0)
  await expect(page.locator('.v7-protection')).toBeVisible()
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toBeEnabled()
})

test('失败和失联不显示成功或继续释放倒计时', async ({ page }) => {
  await scene(page, { time: '2026-09-28T06:16:00Z' })
  await page.route('**/api/meeting-rooms/usage/confirm', route => route.fulfill({ status: 409, json: {} }))
  await page.getByRole('button', { name: '立即签到', exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByText('已签到', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('timer')).toHaveCount(0)
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ status: 502, json: {} }))
  await page.clock.fastForward(45000)
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
})

test('V6 托管入口按模板选择 V7；非主控仍不能签到', async ({ page }) => {
  await scene(page, { managed: true, control: false })
  await expect(page.locator('.door.v7')).toBeVisible()
  await expect(page.getByText('请在本会议室主控门牌签到')).toBeVisible()
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
})

test('V7 官方方案保留扫码入口', async ({ page }) => {
  await scene(page, { owner: 'official' })
  await expect(page.locator('.checkin-qr')).toBeVisible()
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
})

test('V7 软件模板预设仅修改草稿，页面切换不改业务规则', async ({ page }) => {
  const state = await fixture(page)
  await page.goto('/control')
  await page.getByRole('button', { name: '软件模板', exact: true }).click()
  await page.getByRole('button', { name: '新建软件模板' }).click()
  await page.getByLabel('模板名称').fill('V7 品牌签到')
  await page.getByLabel('门牌界面', { exact: true }).selectOption('v7')
  await page.getByLabel('签到方案', { exact: true }).selectOption('v5')
  await expect(page.getByLabel('开始后宽限（分钟）')).toHaveValue('10')
  await page.getByRole('button', { name: '使用会前 5 分钟／会后 5 分钟预设' }).click()
  await expect(page.getByLabel('开始后宽限（分钟）')).toHaveValue('5')
  await expect(page.getByLabel('待释放补确认（秒）')).toHaveValue('0')
  await expect(page.getByLabel('运行模式', { exact: true })).toHaveValue('off')
  expect(state.writes).toHaveLength(0)
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  expect(state.writes.at(-1)?.body.spec).toMatchObject({ display_version: 'v7', rules: { early_minutes: 5, grace_minutes: 5, release_delay_seconds: 0, mode: 'off' } })
  expect(state.configuration.deployments).toHaveLength(0)
})

test('V7 模板预览始终只读', async ({ page }) => {
  await fixture(page)
  await page.route('**/api/room-control/preview?**', route => {
    const now = Date.now()
    return route.fulfill({ json: { data: { room: { room_id: 'omm_beijing', name: '只读预览', enabled: true, capacity: 4 }, usage_owner: 'v5', events: [], server_time: new Date(now).toISOString(), synced_at: new Date(now).toISOString(), valid_until: new Date(now + 60000).toISOString() } } })
  })
  await page.goto('/control')
  await page.getByRole('button', { name: '软件模板', exact: true }).click()
  await page.getByRole('button', { name: '新建软件模板' }).click()
  await page.getByLabel('门牌界面', { exact: true }).selectOption('v7')
  await page.getByLabel('预览会议室').selectOption('omm_beijing')
  await page.getByRole('button', { name: '预览当前草稿', exact: true }).click()
  await expect(page.getByText('V7 预览 · 操作不可用')).toBeVisible()
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
})

test('保护预约截止不声称正在释放', async ({ page }) => {
  await scene(page, { time: '2026-09-28T06:20:00Z', paused: true })
  await expect(page.getByText('签到窗口已结束', { exact: true })).toBeVisible()
  await expect(page.getByText('正在同步释放状态', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
})

test('凭证撤销后隐藏动作和倒计时', async ({ page }) => {
  await scene(page, { time: '2026-09-28T06:16:00Z' })
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toBeEnabled()
  await page.route('**/api/meeting-rooms/usage', route => route.fulfill({ status: 401, json: {} }))
  await page.clock.fastForward(10000)
  await expect(page.getByText('签到暂不可用', { exact: true })).toBeVisible()
  await expect(page.getByRole('timer')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
})

test('无补签到窗口在五分钟截止时隐藏按钮，等待核验结果', async ({ page }) => {
  const state = await scene(page, { time: '2026-09-28T06:19:59Z', buffer: 0 })
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toBeEnabled()
  await page.clock.fastForward(1000)
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
  state.record.state = 'waiting'
  state.can_confirm = false
  await page.clock.fastForward(10000)
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
  await expect(page.getByText('释放前补签到 · 剩余', { exact: true })).toHaveCount(0)
  await expect(page.getByText('本次预约已释放', { exact: true })).toHaveCount(0)
})
