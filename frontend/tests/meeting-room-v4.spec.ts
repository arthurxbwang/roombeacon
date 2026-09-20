import { expect, test } from '@playwright/test'

const qr = 'data:image/svg+xml;base64,' + Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"/>').toString('base64')
const schedule = {
  room: { room_id: 'omm_fixture', name: '201', capacity: 14, enabled: true },
  server_time: '2026-09-20T08:10:00Z', synced_at: '2026-09-20T08:10:00Z', valid_until: '2026-09-20T08:15:00Z',
  titles_available: true, checkin_qr: qr,
  events: [
    { uid: 'current', original_time: 0, summary: '当前会议', organizer: '测试人员', start_time: '2026-09-20T08:00:00Z', end_time: '2026-09-20T09:00:00Z' },
    { uid: 'next', original_time: 0, summary: '产品方案及跨团队技术设计评审会议', organizer: '测试组织者甲', start_time: '2026-09-20T09:30:00Z', end_time: '2026-09-20T10:30:00Z' },
    { uid: 'tomorrow', original_time: 0, summary: '下一阶段项目实施及资源安排讨论会议', organizer: '测试组织者乙', start_time: '2026-09-21T01:00:00Z', end_time: '2026-09-21T02:00:00Z' },
  ],
}
// The 1920×1080 tablet uses density 240: its WebView viewport is 1280×720.
for (const height of [800, 720]) for (const version of ['v4', 'default']) test(`V4 ${version} 1280×${height} 双会议完整、无边框、保留签到和灯控`, async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height })
  await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: schedule } }))
  await page.goto('/room-display.html' + (version === 'v4' ? '?version=v4' : ''))
  await expect(page.locator('.door')).toHaveClass(/v4/)
  await expect(page.locator('.checkin-qr')).toBeVisible()
  await expect(page.locator('.door')).toHaveAttribute('data-terminal-state', 'busy')
  await expect(page.locator('.agenda article')).toHaveCount(2)
  const geometry = await page.locator('.door').evaluate(el => {
    const body = el.querySelector('.agenda-body')!
    const cards = [...el.querySelectorAll('.agenda article')]
    return {
      overflow: el.scrollHeight - el.clientHeight,
      agendaOverflow: body.scrollHeight - body.clientHeight,
      cardsFit: cards.every(card => card.getBoundingClientRect().bottom <= body.getBoundingClientRect().bottom + 1 && card.scrollHeight <= card.clientHeight + 1),
      border: getComputedStyle(el, '::after').content,
    }
  })
  expect(geometry).toEqual({ overflow: 0, agendaOverflow: 0, cardsFit: true, border: 'none' })
  await page.mouse.move(640, height - 20)
  await page.mouse.wheel(0, 400)
  await expect.poll(() => page.locator('.door').evaluate(el => el.scrollTop)).toBe(0)
  await page.screenshot({ path: testInfo.outputPath('v4-fixture.png') })
})
