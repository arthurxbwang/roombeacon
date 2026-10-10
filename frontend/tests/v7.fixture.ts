import type { Page } from '@playwright/test'

export async function scene(page: Page, options: { time?: string; phase?: string; height?: number; dark?: boolean; mode?: string; paused?: boolean; verified?: boolean; managed?: boolean; control?: boolean; owner?: string; deadline?: string; releaseEnabled?: boolean; buffer?: number; language?: 'zh-CN' | 'en'; organizer?: string; private?: boolean; empty?: boolean } = {}) {
  const time = options.time || '2026-09-28T06:10:00Z'
  await page.clock.install({ time: new Date(Date.parse(time) - 1000) })
  await page.clock.pauseAt(new Date(time))
  await page.setViewportSize({ width: 1280, height: options.height || 720 })
  await page.addInitScript(() => {
    localStorage.setItem('argus_room_display', 'fixture')
    localStorage.setItem('argus_room_usage_v5:omm_fixture', 'usage:omm_fixture:' + 'a'.repeat(43))
  })
  const occurrence = { uid: 'fixture', original_time: 0, start_time: '2026-09-28T06:15:00Z', end_time: '2026-09-28T06:30:00Z' }
  const inactive = options.empty || Date.parse(time) < Date.parse(occurrence.start_time) - 5 * 60000
  const state = { room_id: 'omm_fixture', enabled: true, release_enabled: options.releaseEnabled ?? true, paused: options.paused ?? false, target_id: 'a'.repeat(64), can_confirm: true, can_end: false,
    policy: { owner: options.owner || 'v5', mode: options.mode || 'auto', early_minutes: 5, grace_minutes: 5, release_delay_seconds: options.buffer ?? 60, native_policy_cleared: true, release_verified: true, revision: 'fixture' },
    record: { id: 'a'.repeat(64), state: options.phase || 'pending', verified: options.verified ?? true, deadline: options.deadline || '2026-09-28T06:20:00Z', occurrence,
      ...(options.phase === 'waiting' ? { release_at: options.buffer === 0 ? '2026-09-28T06:20:00Z' : '2026-09-28T06:21:00Z' } : {}) } }
  const currentTime = () => page.evaluate(() => Date.now())
  await page.route('**/api/meeting-rooms/display', async route => route.fulfill({ json: { data: {
    room: { room_id: 'omm_fixture', name: 'V7 模拟会议室', capacity: 4, enabled: true },
    server_time: new Date(await currentTime()).toISOString(), synced_at: time, valid_until: '2026-09-28T07:00:00Z', usage_owner: options.owner || 'v5', titles_available: true,
    display_preferences: { theme_mode: options.dark ? 'dark' : 'light', language: options.language || 'zh-CN', display_version: options.managed ? 'v7' : 'v6', usage_control: options.control !== false, ...(options.private===undefined?{}:{show_meeting_titles:!options.private}) },
    events: options.empty ? [] : [{ ...occurrence, summary: '模拟预约 · 非真实会议', organizer: options.organizer ?? '测试数据' }, { ...occurrence, uid: 'next', start_time: '2026-09-28T06:30:00Z', end_time: '2026-09-28T06:45:00Z', summary: '下一场模拟预约', organizer: options.organizer ?? '测试数据' }],
    checkin_qr: 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="white"/></svg>'),
  } } }))
  for (const path of ['usage', 'usage/heartbeat']) await page.route(`**/api/meeting-rooms/${path}`, async route => {
    const now = await currentTime()
    await route.fulfill({ json: { data: { ...state, ...(inactive ? { target_id: null, record: null, can_confirm: false } : {}), server_time: new Date(now).toISOString(), valid_until: new Date(now + 30000).toISOString() } } })
  })
  await page.goto('/room-display.html?version=' + (options.managed ? 'v6&managed=1' : 'v7'))
  return state
}
