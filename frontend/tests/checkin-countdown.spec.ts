import { expect, test, type Page } from '@playwright/test'

async function scene(page: Page, phase = 'pending', options: { paused?: boolean; verified?: boolean; mode?: string; bound?: boolean; validUntil?: string } = {}) {
  await page.clock.install({ time: new Date('2026-09-22T08:01:00Z') })
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.addInitScript(bound => {
    localStorage.setItem('argus_room_display', 'fixture')
    if (bound) localStorage.setItem('argus_room_usage_v5:omm_fixture', 'usage:omm_fixture:' + 'a'.repeat(43))
  }, options.bound !== false)
  const occurrence = { uid: 'fixture', original_time: 0, start_time: '2026-09-22T08:00:00Z', end_time: '2026-09-22T09:00:00Z' }
  const state = { room_id: 'omm_fixture', enabled: true, paused: options.paused ?? false,
    target_id: 'a'.repeat(64), server_time: '2026-09-22T08:01:00Z', valid_until: options.validUntil || '2026-09-22T08:01:30Z', can_confirm: true, can_end: false,
    policy: { owner: 'v5', mode: options.mode || 'auto', early_minutes: 10, grace_minutes: 10, release_delay_seconds: 60, native_policy_cleared: true, release_verified: true, revision: 'test' },
    record: { id: 'a'.repeat(64), state: phase, verified: options.verified ?? true, deadline: '2026-09-22T08:10:00Z', occurrence,
      ...(phase === 'waiting' ? { release_at: '2026-09-22T08:01:45Z' } : {}) } }
  await page.route('**/api/meeting-rooms/display', async route => route.fulfill({ json: { data: {
    room: { room_id: 'omm_fixture', name: '仅布局测试 · 模拟会议室', capacity: 4, enabled: true },
    server_time: await page.evaluate(() => new Date().toISOString()), synced_at: state.server_time, valid_until: '2026-09-22T08:20:00Z', usage_owner: 'v5', titles_available: true,
    events: [{ ...occurrence, summary: '模拟预约 · 非线上签到', organizer: '测试数据' }],
  } } }))
  await page.route('**/api/meeting-rooms/usage', route => route.fulfill({ json: { data: state } }))
  await page.route('**/api/meeting-rooms/usage/heartbeat', route => route.fulfill({ json: { data: state } }))
  await page.goto('/room-display.html?version=v5')
}

test('签到倒计时逐秒变化，签到区无独立背景或边框', async ({ page }, info) => {
  await scene(page)
  await expect(page.getByRole('button', { name: '签到', exact: true })).toBeEnabled()
  await expect(page.getByLabel('签到倒计时')).toHaveText('09:00')
  await page.clock.fastForward(1000)
  await expect(page.getByLabel('签到倒计时')).toHaveText('08:59')
  const style = await page.locator('.usage-body').evaluate(e => ({ border: getComputedStyle(e).borderTopWidth, background: getComputedStyle(e).backgroundColor }))
  expect(style).toEqual({ border: '0px', background: 'rgba(0, 0, 0, 0)' })
  expect(await page.locator('.door').evaluate(e => e.scrollHeight - e.clientHeight)).toBe(0)
  await expect(page.getByText('管理员配置', { exact: true })).toHaveCount(0)
  await page.screenshot({ path: info.outputPath('checkin-countdown.png') })
})

test('待释放显示服务器释放倒计时，网络失败不伪报已释放', async ({ page }, info) => {
  await scene(page, 'waiting')
  await expect(page.getByLabel('释放倒计时')).toHaveText('00:45')
  await page.clock.fastForward(1000)
  await expect(page.getByLabel('释放倒计时')).toHaveText('00:44')
  expect(await page.locator('.usage-body').evaluate(e => e.scrollHeight - e.clientHeight)).toBe(0)
  await page.screenshot({ path: info.outputPath('release-countdown.png') })
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ status: 502, json: {} }))
  await page.clock.fastForward(45000)
  await expect(page.getByLabel('释放倒计时')).toHaveCount(0)
  await expect(page.getByText('本次预约已释放', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
})

for (const [phase, options] of [
  ['confirmed', {}], ['blocked', {}], ['waiting', { paused: true }], ['waiting', { verified: false }], ['waiting', { mode: 'observe' }],
] as const) test(`保护状态不显示释放倒计时：${phase} ${JSON.stringify(options)}`, async ({ page }) => {
  await scene(page, phase, options)
  await expect(page.locator('.usage-state')).toBeVisible()
  await expect(page.getByLabel('释放倒计时')).toHaveCount(0)
})

test('未配置时只给出简短不可用提示，保留设备设置入口', async ({ page }) => {
  await scene(page, 'pending', { bound: false })
  await expect(page.getByText('签到暂不可用', { exact: true })).toBeVisible()
  await expect(page.getByText('确认使用尚未配置', { exact: true })).toHaveCount(0)
  await expect(page.getByText('管理员配置', { exact: true })).toHaveCount(0)
  await page.getByText('设备设置', { exact: true }).click()
  await expect(page.getByLabel('V5 操作凭证')).toBeVisible()
})


test('倒计时到零等待服务器核验，不自行显示释放成功', async ({ page }) => {
  await scene(page, 'waiting', { validUntil: '2026-09-22T08:02:30Z' })
  await expect(page.getByLabel('释放倒计时')).toHaveText('00:45')
  await page.clock.fastForward(45000)
  await expect(page.getByLabel('释放倒计时')).toHaveCount(0)
  await expect(page.getByText('正在同步释放状态', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
  await expect(page.getByText('本次预约已释放', { exact: true })).toHaveCount(0)
})
