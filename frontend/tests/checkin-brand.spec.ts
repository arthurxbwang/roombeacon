import { expect, test } from '@playwright/test'

const qr = 'data:image/svg+xml;base64,' + Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><text x="15" y="100">TEST ONLY</text></svg>').toString('base64')
for (const height of [720, 800]) for (const theme of ['light', 'dark']) {
  test(`V4 签到动图前景完整可见 ${height} ${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 1280, height })
    await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
    await page.route('**/api/meeting-rooms/display', route => route.fulfill({ json: { data: {
      room: { room_id: 'omm_fixture', name: '203 测试', capacity: 9, enabled: true },
      server_time: '2026-09-20T08:10:00Z', synced_at: '2026-09-20T08:10:00Z', valid_until: '2026-09-20T08:15:00Z',
      titles_available: true, checkin_qr: qr, events: [],
      daylight: { city: '北京', timezone: 'Asia/Shanghai', valid_until: '2026-09-21T00:00:00Z',
        windows: theme === 'light' ? [{ start: '2026-09-20T00:00:00Z', end: '2026-09-20T12:00:00Z' }] : [] },
    } } }))
    await page.goto('/room-display.html?version=v4')
    await expect(page.locator('.door')).toHaveClass(new RegExp(`theme-${theme}`))
    await expect(page.locator('.checkin-qr')).toBeVisible()
    await expect.poll(() => page.locator('.brand-art img').evaluate(img => (img as HTMLImageElement).complete)).toBe(true)
    const inspect = () => page.locator('.brand-art').evaluate(art => {
      const r = art.getBoundingClientRect()
      let top = r.top, bottom = r.bottom, left = r.left, right = r.right
      for (let p = art.parentElement; p; p = p.parentElement) {
        const style = getComputedStyle(p), box = p.getBoundingClientRect()
        if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) { top = Math.max(top, box.top); bottom = Math.min(bottom, box.bottom) }
        if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) { left = Math.max(left, box.left); right = Math.min(right, box.right) }
      }
      // Temporarily allow hit testing to check the visual stacking order of the decoration.
      const img = art.querySelector('img')!
      const previous = img.style.pointerEvents
      img.style.pointerEvents = 'auto'
      const foreground = [0.05, 0.5, 0.95].every(f => document.elementFromPoint(r.x + r.width / 2, r.y + r.height * f) === img)
      img.style.pointerEvents = previous
      const code = document.querySelector('.checkin-qr')!.getBoundingClientRect()
      return { unclipped: top <= r.top + 1 && bottom >= r.bottom - 1 && left <= r.left + 1 && right >= r.right - 1,
        foreground, inViewport: r.top >= 0 && r.bottom <= innerHeight,
        qrBelow: code.top >= r.bottom && code.bottom <= innerHeight,
        pageOverflow: document.querySelector('.door')!.scrollHeight - document.querySelector('.door')!.clientHeight }
    })
    expect(await inspect()).toEqual({ unclipped: true, foreground: true, inViewport: true, qrBelow: true, pageOverflow: 0 })
    // The GIF's blank top margin must blend into the page, including in night mode.
    const art = (await page.locator('.brand-art').boundingBox())!
    const blank = await page.screenshot({ clip: { x: Math.floor(art.x + art.width / 2), y: Math.floor(art.y) + 1, width: 1, height: 1 } })
    const background = await page.screenshot({ clip: { x: 2, y: 2, width: 1, height: 1 } })
    expect(blank.equals(background)).toBe(true)
    await page.mouse.move(600, height - 100)
    await page.mouse.wheel(0, 300)
    expect(await inspect()).toEqual({ unclipped: true, foreground: true, inViewport: true, qrBelow: true, pageOverflow: 0 })
  })
}
