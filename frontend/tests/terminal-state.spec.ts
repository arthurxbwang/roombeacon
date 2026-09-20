import { expect, test } from '@playwright/test'

const room = { room_id: 'omm_fixture', name: '灯控模拟测试', capacity: 4, enabled: true }
const base = { room, server_time: '2026-09-20T08:00:00Z', synced_at: '2026-09-20T08:00:00Z', valid_until: '2026-09-20T08:05:00Z', titles_available: false, events: [] }
const event = { uid: 'fixture', original_time: 0, start_time: '2026-09-20T07:30:00Z', end_time: '2026-09-20T08:30:00Z' }
for (const [name, data, state] of [
  ['空闲', base, 'free'],
  ['使用中', { ...base, events: [event] }, 'busy'],
  ['即将开始', { ...base, events: [{ ...event, start_time: '2026-09-20T08:10:00Z' }] }, 'soon'],
  ['停用', { ...base, room: { ...room, enabled: false } }, 'unknown'],
  ['过期', { ...base, valid_until: base.server_time }, 'unknown'],
] as const) test(`灯控状态契约：${name}`, async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data } }))
  await page.goto('/room-display.html?version=v3')
  await expect(page.locator('.room-identity h1')).toHaveText(room.name)
  await expect(page.locator('main')).toHaveAttribute('data-terminal-protocol', '1')
  await expect(page.locator('main')).toHaveAttribute('data-terminal-state', state)
})

test('灯控失联、恢复、撤销和未绑定均不误报空闲', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
  await page.clock.install()
  let status = 200
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ status, json: status === 200 ? { data: base } : {} }))
  await page.goto('/room-display.html?version=v3')
  await expect(page.locator('main')).toHaveAttribute('data-terminal-state', 'free')
  for (const code of [503, 200, 401]) {
    status = code
    await page.clock.fastForward(16000)
    await expect(page.locator('main')).toHaveAttribute('data-terminal-state', code === 200 ? 'free' : 'unknown')
  }
  await page.reload()
  await expect(page.locator('main')).toHaveAttribute('data-terminal-state', 'unknown')
})
