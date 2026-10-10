import { expect, test } from '@playwright/test'
import { scene } from './v7.fixture'
import { fixture } from './configuration.fixture'

for (const height of [720, 800]) for (const dark of [false, true]) for (const phase of ['soon', 'busy', 'free', 'empty']) {
  test(`保密门牌布局 1280×${height} ${dark ? '夜间' : '白天'} ${phase}`, async ({ page }, info) => {
    await scene(page, { height, dark, managed: true, private: true, empty: phase === 'empty',
      time: phase === 'busy' ? '2026-09-28T06:16:00Z' : phase === 'free' ? '2026-09-28T05:30:00Z' : undefined })
    await expect(page.locator('.door.v7.private-meetings')).toBeVisible()
    await expect(page.locator('.meeting-detail h2,.agenda article h4')).toHaveCount(0)
    await expect(page.locator('body')).not.toContainText('模拟预约')
    await expect(page.locator('[title*="模拟预约"]')).toHaveCount(0)
    await expect(page.getByText('V7 模拟会议室', { exact: true })).toBeVisible()
    if (phase !== 'empty') {
      await expect(page.locator('.meeting-time')).toHaveText('14:15 — 14:30')
      await expect(page.locator('.meeting-detail .organizer')).toHaveText('组织者 · 测试数据')
      await expect(page.locator('.meeting-detail .detail-label')).toBeVisible()
    }
    if (phase === 'soon' || phase === 'busy') await expect(page.getByRole('button', { name: '立即签到', exact: true })).toBeEnabled()
    else await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
    const layout = await page.locator('.door').evaluate(door => {
      const panels = ['.primary-info', '.usage-body', '.agenda-body', '.timeline']
        .map(selector => door.querySelector(selector)).filter((e): e is HTMLElement => !!e)
      const rects = panels.map(e => e.getBoundingClientRect())
      return { overflow: door.scrollHeight > door.clientHeight + 1 || door.scrollWidth > door.clientWidth + 1,
        clipped: panels.some(e => e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1),
        outside: rects.some(r => r.bottom > innerHeight + 1 || r.top < 0 || r.right > innerWidth + 1 || r.left < 0),
        overlap: rects.some((a, i) => rects.slice(i + 1).some(b => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top)) }
    })
    expect(layout).toEqual({ overflow: false, clipped: false, outside: false, overlap: false })
    await page.screenshot({ path: info.outputPath('private-template.png') })
  })
}

test('保密模板签到、刷新、失联都不重新显示会议名称', async ({ page }) => {
  const state = await scene(page, { managed: true, private: true })
  await page.route('**/api/meeting-rooms/usage/confirm', route => {
    state.record.state = 'confirmed'; state.can_confirm = false
    return route.fulfill({ json: { data: { ...state, valid_until: '2026-09-28T07:00:00Z' } } })
  })
  await page.getByRole('button', { name: '立即签到', exact: true }).click()
  await expect(page.locator('.v7-status')).toHaveText('已签到')
  await page.reload()
  await expect(page.locator('.v7-status')).toHaveText('已签到')
  await expect(page.locator('.meeting-detail h2,.agenda article h4')).toHaveCount(0)
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ status: 503, json: {} }))
  await page.clock.fastForward(16000)
  await expect(page.getByText('状态暂不可确认', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '立即签到', exact: true })).toHaveCount(0)
  await expect(page.locator('body')).not.toContainText('模拟预约')
})

test('英文与官方扫码保密模板保留原内容，缺字段旧模板继续显示名称', async ({ page }) => {
  await scene(page, { managed: true, private: true, language: 'en', owner: 'official' })
  await expect(page.locator('.checkin-qr')).toBeVisible()
  await expect(page.locator('.meeting-time')).toHaveText('14:15 — 14:30')
  await expect(page.locator('.meeting-detail h2,.agenda article h4')).toHaveCount(0)
  await page.unrouteAll({ behavior: 'wait' })
  await scene(page, { managed: true })
  await expect(page.locator('.meeting-detail h2')).toHaveText('模拟预约 · 非真实会议')
})

test('模板编辑、复制和发布保留显示偏好，草稿预览只读且隐藏名称', async ({ page }) => {
  const state = await fixture(page)
  state.catalog[1].spec = { ...state.catalog[1].spec, display_version: 'v7', show_meeting_titles: false }
  await page.route('**/api/room-control/preview?**', route => {
    const now = Date.now()
    return route.fulfill({ json: { data: { room: { room_id: 'omm_beijing', name: '保密模拟预览', enabled: true, capacity: 4 },
      events: [{ uid: 'fixture', original_time: 0, start_time: new Date(now - 60000).toISOString(), end_time: new Date(now + 60000).toISOString(), summary: '不应显示的模拟主题', organizer: '模拟组织者' }],
      server_time: new Date(now).toISOString(), synced_at: new Date(now).toISOString(), valid_until: new Date(now + 60000).toISOString(), usage_owner: 'official' } } })
  })
  await page.goto('/control')
  await page.getByRole('button', { name: '软件模板', exact: true }).click()
  const item = page.locator('.v6-template-item:visible').filter({ hasText: '测试中文软件' })
  await expect(item).toContainText('隐藏会议名称')
  await item.getByRole('button', { name: '复制', exact: true }).click()
  await expect(page.getByLabel('显示会议名称')).not.toBeChecked()
  await page.getByLabel('预览会议室').selectOption('omm_beijing')
  await page.getByRole('button', { name: '预览当前草稿', exact: true }).click()
  await expect(page.locator('.v6-template-live-preview .meeting-time')).toBeVisible()
  await expect(page.locator('.v6-template-live-preview')).not.toContainText('不应显示的模拟主题')
  expect(state.writes).toHaveLength(0)
  await page.getByLabel('显示会议名称').check()
  await expect(page.locator('.v6-template-live-preview .meeting-detail h2')).toHaveText('不应显示的模拟主题')
  await page.getByLabel('显示会议名称').uncheck()
  await page.getByRole('button', { name: '保存草稿', exact: true }).click()
  expect(state.writes.at(-1)?.body.spec.show_meeting_titles).toBe(false)
  const copy = page.locator('.v6-template-item:visible').filter({ hasText: '测试中文软件 · 副本' })
  await copy.getByRole('button', { name: '发布版本', exact: true }).click()
  expect((state.catalog.at(-1)!.versions[0].spec as { show_meeting_titles: boolean }).show_meeting_titles).toBe(false)
  expect(state.configuration.deployments).toHaveLength(0)
})
