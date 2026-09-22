import { expect, test, type Page } from '@playwright/test'

const id = 'a'.repeat(64)
const fixture = () => ({
  room_id: 'omm_fixture', enabled: true, paused: true, target_id: id,
  server_time: '2026-09-20T08:01:00Z', valid_until: '2026-09-20T08:01:30Z',
  policy: { owner: 'v5', release_delay_seconds: 60, mode: 'observe', early_minutes: 5, grace_minutes: 10, native_policy_cleared: false, release_verified: false, revision: 'rev1' },
  record: { id, state: 'pending', reason: 'monitoring', verified: false, deadline: '2026-09-20T08:10:00Z',
    occurrence: { uid: 'fixture', original_time: 0, start_time: '2026-09-20T08:00:00Z', end_time: '2026-09-20T09:00:00Z' } },
  can_confirm: true, can_end: false,
})
async function mockUsage(page: Page, usage: ReturnType<typeof fixture>) {
  await page.route('**/api/meeting-rooms/usage', route => route.fulfill({ json: { data: usage } }))
  await page.route('**/api/meeting-rooms/usage/heartbeat', route => route.fulfill({ json: { data: usage } }))
}
async function display(page: Page) {
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.addInitScript(() => {
    localStorage.setItem('argus_room_display', 'fixture')
    localStorage.setItem('argus_room_usage_v5:omm_fixture', 'usage:omm_fixture:' + 'a'.repeat(43))
  })
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: {
    room: { room_id: 'omm_fixture', name: 'IT灯塔-Test · 模拟', capacity: 14, enabled: true },
    server_time: '2026-09-20T08:01:00Z', synced_at: '2026-09-20T08:01:00Z', valid_until: '2026-09-20T08:20:00Z',
    titles_available: true, events: [
      { uid: 'fixture', original_time: 0, summary: '测试会议', organizer: '测试组织者', start_time: '2026-09-20T08:00:00Z', end_time: '2026-09-20T09:00:00Z' },
      { uid: 'next', original_time: 0, summary: '下一场测试', organizer: '测试人员', start_time: '2026-09-20T09:30:00Z', end_time: '2026-09-20T10:00:00Z' },
    ],
  } } }))
}

test('V5 观察确认、刷新恢复且保留 V4 默认与灯控', async ({ page }, testInfo) => {
  await display(page)
  const usage = fixture()
  let confirmations = 0
  await mockUsage(page, usage)
  await page.route('**/api/meeting-rooms/usage/confirm', async route => {
    expect(route.request().postDataJSON()).toMatchObject({ occurrence_id: id, policy_revision: 'rev1', session_id: expect.stringMatching(/^[a-f0-9]{32}$/) })
    confirmations++; usage.record.state = 'confirmed'; usage.can_confirm = false
    await route.fulfill({ json: { data: usage } })
  })
  await page.goto('/room-display.html?version=v5')
  await expect(page.locator('.door')).toHaveClass(/v5/)
  await expect(page.getByText('观察模式 · 仅记录，不自动释放')).toBeVisible()
  await expect(page.locator('.door')).toHaveAttribute('data-terminal-state', 'busy')
  await page.getByRole('button', { name: '签到', exact: true }).click()
  await expect(page.getByText('已确认使用', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('已确认使用', { exact: true })).toBeVisible()
  expect(confirmations).toBe(1)
  expect(await page.locator('.door').evaluate(el => el.scrollHeight - el.clientHeight)).toBe(0)
  await page.screenshot({ path: testInfo.outputPath('v5-observe-fixture.png') })
  await page.goto('/room-display.html')
  await expect(page.locator('.door')).toHaveClass(/v4/)
  await expect(page.locator('.door')).not.toHaveClass(/v5/)
  await expect(page.getByRole('complementary', { name: 'V5 确认使用' })).toHaveCount(0)
})

test('旧服务器和功能关闭时 V5 保持预约展示', async ({ page }) => {
  await display(page)
  await page.route('**/api/meeting-rooms/usage', route => route.fulfill({ status: 404, json: {} }))
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByText('当前服务器尚未支持 V5，预约展示不受影响')).toBeVisible()
  await expect(page.locator('.status-text')).toHaveText('使用中')
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
})

test('凭证撤销只清除操作绑定，不清除现有展示绑定', async ({ page }) => {
  await display(page)
  await page.route('**/api/meeting-rooms/usage', route => route.fulfill({ status: 401, json: {} }))
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByText('操作凭证已失效，请重新绑定')).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('argus_room_display'))).toBe('fixture')
  expect(await page.evaluate(() => localStorage.getItem('argus_room_usage_v5:omm_fixture'))).toBeNull()
})

test('确认失败不得显示成功；连续点击不重复发送', async ({ page }) => {
  await display(page)
  let count = 0
  await mockUsage(page, fixture())
  await page.route('**/api/meeting-rooms/usage/confirm', async route => {
    count++
    await new Promise(resolve => setTimeout(resolve, 200))
    await route.fulfill({ status: 502, json: {} })
  })
  await page.goto('/room-display.html?version=v5')
  await page.getByRole('button', { name: '签到', exact: true }).click()
  await expect(page.getByText('操作结果待核实，请等待重新同步')).toBeVisible()
  await expect(page.getByText('已确认使用', { exact: true })).toHaveCount(0)
  expect(count).toBe(1)
})

test('旧接口允许提前结束时页面也不提供入口，签到仍可用', async ({ page }, testInfo) => {
  await display(page)
  const usage = fixture()
  usage.policy.mode = 'auto'; usage.paused = false; usage.can_end = true; usage.record.verified = true
  let ends = 0
  await mockUsage(page, usage)
  await page.route('**/api/meeting-rooms/usage/end', route => { ends++; return route.fulfill({ status: 403 }) })
  await page.route('**/api/meeting-rooms/usage/confirm', route => {
    usage.record.state = 'confirmed'; usage.can_confirm = false
    return route.fulfill({ json: { data: usage } })
  })
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByRole('button', { name: /提前结束|释放本次预约/ })).toHaveCount(0)
  await expect(page.getByText('签到与释放', { exact: true })).toHaveCount(0)
  await expect(page.getByText('确认结果由 RoomBeacon 记录')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '签到', exact: true })).toBeEnabled()
  await page.screenshot({ path: testInfo.outputPath('v5-checkin-pill.png') })
  await page.getByRole('button', { name: '签到', exact: true }).click()
  await expect(page.getByText('已确认使用', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /提前结束|释放本次预约/ })).toHaveCount(0)
  expect(ends).toBe(0)
})

test('过期状态不能确认；不接受其他房间操作状态', async ({ page }) => {
  await display(page)
  const usage = fixture(); usage.valid_until = '2026-09-20T08:00:00Z'
  await mockUsage(page, usage)
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByText('确认状态待同步', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
  usage.room_id = 'omm_other'; usage.valid_until = '2026-09-20T08:30:00Z'
  await page.reload()
  await expect(page.getByText('操作结果待核实，请等待重新同步')).toBeVisible()
})

async function control(page: Page) {
  await display(page)
  await page.addInitScript(() => {
    sessionStorage.setItem('argus_room_control', 'fixture-admin')
    localStorage.setItem('argus_room_version', 'v4')
  })
  await page.route('**/api/room-control/rooms', route => route.fulfill({ json: { data: [
    { room_id: 'omm_fixture', name: 'IT灯塔-Test · 模拟', capacity: 14, enabled: true, region: '北京', location: '北京 / 2F', floor: '2F' },
  ] } }))
}

test('主控 V5 预览不触发操作或改变 V4 偏好', async ({ page }) => {
  await control(page)
  let operations = 0
  await page.route('**/api/meeting-rooms/usage**', route => { operations++; return route.abort() })
  await page.route('**/api/room-control/preview*', route => route.fulfill({ json: { data: {
    room: { room_id: 'omm_fixture', name: 'IT灯塔-Test · 模拟', capacity: 14, enabled: true },
    server_time: '2026-09-20T08:01:00Z', synced_at: '2026-09-20T08:01:00Z', valid_until: '2026-09-20T08:20:00Z',
    titles_available: true, events: [],
  } } }))
  await page.goto('/control')
  await page.getByRole('button', { name: '预览门牌' }).click()
  await page.getByLabel('门牌版本').selectOption('v5')
  await expect(page.getByText('V5 预览 · 操作不可用')).toBeVisible()
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('argus_room_version'))).toBe('v4')
  expect(operations).toBe(0)
})

test('主控保存观察规则并暂停全局释放', async ({ page }) => {
  await control(page)
  const usage = fixture()
  let saved = false, paused = false
  await page.route('**/api/room-control/usage/omm_fixture', route => route.fulfill({ json: {
    data: { usage, audit: [], global_audit: [], writes_enabled: false },
  } }))
  await page.route('**/api/room-control/usage/omm_fixture/policy', route => {
    const data = route.request().postDataJSON()
    expect(data.mode).toBe('observe'); expect(data.grace_minutes).toBe(12)
    saved = true; usage.policy = data
    return route.fulfill({ json: { data } })
  })
  await page.route('**/api/room-control/usage-pause', route => {
    expect(route.request().postDataJSON()).toEqual({ paused: true }); paused = true
    return route.fulfill({ json: { data: { paused: true } } })
  })
  await page.goto('/control')
  await page.getByRole('button', { name: 'V5 规则', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'V5 使用规则 · IT灯塔-Test · 模拟' })).toBeVisible()
  await page.getByLabel('开始后宽限（分钟）').fill('12')
  await page.getByRole('button', { name: '保存房间规则' }).click()
  await expect(page.getByText('已保存，请核对当前状态')).toBeVisible()
  expect(saved).toBe(true)
  await expect(page.getByRole('button', { name: '解除全局暂停' })).toBeDisabled()
  await page.getByRole('button', { name: '暂停所有房间释放' }).click()
  await expect.poll(() => paused).toBe(true)
})

test('确认失败后查询恢复与刷新也不能重新上报可释放', async ({ page }) => {
  await display(page)
  const usage = fixture()
  await mockUsage(page, usage)
  const reports: string[] = []
  await page.route('**/api/meeting-rooms/usage/heartbeat', route => {
    reports.push(route.request().postDataJSON().operation_state)
    return route.fulfill({ json: { data: usage } })
  })
  await page.route('**/api/meeting-rooms/usage/confirm', route => route.abort())
  await page.goto('/room-display.html?version=v5')
  await page.getByRole('button', { name: '签到', exact: true }).click()
  await expect(page.getByText('操作结果待核实，请等待重新同步')).toBeVisible()
  expect(reports).toContain('submitting')
  reports.length = 0
  await page.reload()
  await expect.poll(() => reports.length).toBeGreaterThan(0)
  expect(reports).toEqual(['uncertain'])
  expect(await page.evaluate(() => localStorage.getItem('argus_room_usage_v5:omm_fixture:unresolved'))).toBe(id)
})

test('待释放可补确认，发送前核验由当前页面回复', async ({ page }) => {
  await display(page)
  const usage = { ...fixture(), record: { ...fixture().record, state: 'waiting', release_at: '2026-09-20T08:11:00Z', challenge_id: 'b'.repeat(32) } }
  await mockUsage(page, usage)
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByText('尚未确认 · 即将释放', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '签到', exact: true })).toBeEnabled()
  usage.record.state = 'checking'; usage.can_confirm = false
  let ack = ''
  await page.route('**/api/meeting-rooms/usage/heartbeat', route => {
    ack = route.request().postDataJSON().challenge_id
    return route.fulfill({ json: { data: usage } })
  })
  await page.reload()
  await expect.poll(() => ack).toBe('b'.repeat(32))
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
})

test('V5 官方方案不提供操作；V4 遇到 V5 房间提示正确入口', async ({ page }) => {
  await display(page)
  const usage = fixture(); usage.policy.owner = 'official'; usage.policy.mode = 'off'
  await mockUsage(page, usage)
  let reports = 0
  await page.route('**/api/meeting-rooms/usage/heartbeat', route => { reports++; return route.abort() })
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByText('本房间使用官方方案，请切换到 V4')).toBeVisible()
  expect(reports).toBe(0)
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: {
    room: { room_id: 'omm_fixture', name: 'IT灯塔-Test', capacity: 4, enabled: true }, events: [], usage_owner: 'v5',
    server_time: '2026-09-20T08:01:00Z', synced_at: '2026-09-20T08:01:00Z', valid_until: '2026-09-20T08:20:00Z',
    checkin_qr: 'data:image/svg+xml,fixture', titles_available: true,
  } } }))
  await page.goto('/room-display.html?version=v4')
  await expect(page.getByText('本房间使用 V5 确认，请切换到 V5 页面')).toBeVisible()
  await expect(page.locator('.checkin-card')).toHaveCount(0)
})

test('日程查询短暂失败后仍保持本次预约保护', async ({ page }) => {
  await page.clock.install()
  await display(page)
  const usage = fixture()
  await mockUsage(page, usage)
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByRole('button', { name: '签到', exact: true })).toBeEnabled()
  await page.route('**/api/meeting-rooms/display', route => route.fulfill({ status: 502, json: {} }))
  await page.clock.fastForward(15000)
  await expect(page.locator('.status-text')).toHaveText('状态暂不可确认')
  expect(await page.evaluate(() => localStorage.getItem('argus_room_usage_v5:omm_fixture:unresolved'))).toBe(id)
})

for (const scenario of ['success', 'denied', 'failed'] as const) {
  test(`主控显式签到测试隔离：${scenario}`, async ({ page }) => {
    await control(page)
    const usage = fixture()
    let confirmations = 0, terminalRequests = 0
    await page.route('**/api/meeting-rooms/usage**', route => { terminalRequests++; return route.abort() })
    await page.route('**/api/room-control/preview*', route => route.fulfill({ json: { data: {
      room: { room_id: 'omm_fixture', name: 'IT灯塔-Test · 模拟', capacity: 4, enabled: true },
      server_time: '2026-09-20T08:01:00Z', synced_at: '2026-09-20T08:01:00Z', valid_until: '2026-09-20T08:20:00Z',
      titles_available: true, events: [{ ...usage.record.occurrence, summary: '测试会议' }],
    } } }))
    await page.route('**/api/room-control/usage/omm_fixture', route => route.fulfill({ json: { data: {
      usage, control_confirm_enabled: scenario !== 'denied', writes_enabled: scenario !== 'denied', audit: [], global_audit: [],
    } } }))
    await page.route('**/api/room-control/usage/omm_fixture/confirm', route => {
      expect(route.request().headers().authorization).toBe('Bearer fixture-admin')
      expect(route.request().postDataJSON()).toMatchObject({ occurrence_id: id, policy_revision: 'rev1' })
      confirmations++
      if (scenario === 'failed') return route.fulfill({ status: 409, json: {} })
      usage.record.state = 'confirmed'; usage.can_confirm = false
      return route.fulfill({ json: { data: usage } })
    })
    await page.goto('/control')
    await page.getByRole('button', { name: '预览门牌', exact: true }).click()
    await page.getByLabel('门牌版本').selectOption('v5')
    if (scenario === 'denied') {
      await expect(page.getByText('V5 预览 · 操作不可用')).toBeVisible()
      await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
    } else {
      await expect(page.getByRole('button', { name: '进入签到测试' })).toHaveCount(0)
      await expect(page.getByText('主控签到测试 · 仅记录确认；自动释放仍需平板在线')).toBeVisible()
      expect(confirmations).toBe(0)
      await page.getByRole('button', { name: '签到', exact: true }).click()
      if (scenario === 'success') await expect(page.getByText('已确认使用', { exact: true })).toBeVisible()
      else {
        await expect(page.getByText('预约或规则已变化，请刷新后核对')).toBeVisible()
        await expect(page.getByText('已确认使用', { exact: true })).toHaveCount(0)
      }
      expect(confirmations).toBe(1)
    }
    await expect(page.getByRole('button', { name: '提前结束', exact: true })).toHaveCount(0)
    expect(terminalRequests).toBe(0)
    expect(await page.evaluate(() => localStorage.getItem('argus_room_usage_v5:omm_fixture'))).toBe('usage:omm_fixture:' + 'a'.repeat(43))
  })
}

test('白名单主控单次点击就提交签到，并保留服务器回执', async ({ page }) => {
  await control(page)
  const usage = fixture()
  const receiptTime = '2026-09-20T08:02:00Z'
  let confirmations = 0
  let ended = false
  await page.route('**/api/room-control/preview*', route => route.fulfill({ json: { data: {
    room: { room_id: 'omm_fixture', name: 'IT灯塔-Test · 模拟', capacity: 4, enabled: true },
    server_time: '2026-09-20T08:01:00Z', synced_at: '2026-09-20T08:01:00Z', valid_until: '2026-09-20T08:20:00Z',
    titles_available: true, events: ended ? [] : [{ ...usage.record.occurrence, summary: '测试会议' }],
  } } }))
  await page.route('**/api/room-control/usage/omm_fixture', route => route.fulfill({ json: { data: {
    usage: ended ? { ...usage, record: null, target_id: null, can_confirm: false } : usage,
    control_confirm_enabled: true, writes_enabled: true,
    audit: confirmations ? [{ time: receiptTime, action: 'control_confirm', state: 'confirmed' }] : [],
  } } }))
  await page.route('**/api/room-control/usage/omm_fixture/confirm', route => {
    confirmations++; usage.record.state = 'confirmed'; usage.can_confirm = false
    return route.fulfill({ json: { data: usage } })
  })
  await page.goto('/control')
  await page.getByRole('button', { name: '预览门牌', exact: true }).click()
  await page.getByLabel('门牌版本').selectOption('v5')
  await expect(page.getByRole('button', { name: '进入签到测试' })).toHaveCount(0)
  await page.getByRole('button', { name: '签到', exact: true }).click()
  await expect(page.getByText('已确认使用', { exact: true })).toBeVisible()
  expect(confirmations).toBe(1)
  ended = true
  await page.reload()
  await page.getByRole('button', { name: '预览门牌', exact: true }).click()
  await page.getByLabel('门牌版本').selectOption('v5')
  await expect(page.getByText('当前没有可签到的预约', { exact: true })).toBeVisible()
  await expect(page.getByText(/最近一次签到成功/)).toContainText('16:02')
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
  expect(confirmations).toBe(1)
})

for (const height of [720, 800]) test(`V5 三列标题与内容下沿对齐 ${height}`, async ({ page }, testInfo) => {
  await display(page)
  await page.setViewportSize({ width: 1280, height })
  const usage = fixture()
  usage.policy.mode = 'auto'; usage.paused = false
  usage.record.state = 'blocked'; usage.record.reason = 'missed_window'; usage.can_confirm = false
  usage.record.deadline = '2026-09-20T08:00:00Z'
  await mockUsage(page, usage)
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByText('自动释放已暂停', { exact: true })).toBeVisible()
  await expect(page.getByText('未在截止前确认，将按规则释放预约')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '签到', exact: true })).toHaveCount(0)
  const geometry = await page.evaluate(() => {
    const rect = (s: string) => document.querySelector(s)!.getBoundingClientRect()
    const headers = ['.status-text', '.agenda-header'].map(s => rect(s).bottom)
    const panels = ['.primary-body', '.usage-body', '.agenda-body'].map(s => rect(s).bottom)
    return { headers: Math.max(...headers) - Math.min(...headers), panels: Math.max(...panels) - Math.min(...panels),
      overflow: ['.door', '.usage-body'].map(s => { const e = document.querySelector(s)!; return e.scrollHeight - e.clientHeight }) }
  })
  expect(geometry.headers).toBeLessThanOrEqual(1)
  expect(geometry.panels).toBeLessThanOrEqual(1)
  expect(geometry.overflow).toEqual([0, 0])
  await page.screenshot({ path: testInfo.outputPath(`v5-aligned-${height}.png`) })
})

test('当前会议确认时也为下一场独立上报监控，确认只提交当前实例', async ({ page }) => {
  await display(page)
  const next = 'b'.repeat(64)
  const usage = { ...fixture(), monitored_occurrence_ids: [id, next] }
  const reports: { occurrence_id: string; monitored_occurrence_ids: string[]; operation_state: string }[] = []
  const confirmed: string[] = []
  await mockUsage(page, usage)
  await page.route('**/api/meeting-rooms/usage/heartbeat', route => {
    reports.push(route.request().postDataJSON())
    return route.fulfill({ json: { data: usage } })
  })
  await page.route('**/api/meeting-rooms/usage/confirm', route => {
    confirmed.push(route.request().postDataJSON().occurrence_id)
    usage.record.state = 'confirmed'; usage.can_confirm = false
    return route.fulfill({ json: { data: usage } })
  })
  await page.goto('/room-display.html?version=v5')
  await expect.poll(() => reports.length).toBeGreaterThan(0)
  expect(reports[0]).toMatchObject({ occurrence_id: id, monitored_occurrence_ids: [id, next], operation_state: 'ready' })
  await page.getByRole('button', { name: '签到', exact: true }).click()
  await expect(page.getByText('已确认使用', { exact: true })).toBeVisible()
  expect(reports.some(r => r.operation_state === 'submitting' && r.monitored_occurrence_ids.includes(next))).toBe(true)
  expect(confirmed).toEqual([id])
})

test('自动核验待完成时允许签到，但不宣称会自动释放', async ({ page }) => {
  await display(page)
  const usage = { ...fixture(), auto_verify_enabled: true }
  usage.policy.mode = 'auto'; usage.paused = false
  await mockUsage(page, usage)
  await page.goto('/room-display.html?version=v5')
  await expect(page.getByText('正在核验预约，暂不自动释放')).toBeVisible()
  await expect(page.getByText('未签到将按规则释放预约')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '签到', exact: true })).toBeEnabled()
})
