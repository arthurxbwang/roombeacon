import { expect, test } from '@playwright/test'

for (const ready of [true, false]) {
  test(`页面发布 ${ready ? '资源完整后更新并保留绑定' : '资源缺失时不刷新'}`, async ({ page }) => {
    await page.clock.install()
    await page.addInitScript(() => localStorage.setItem('argus_room_display', 'fixture'))
    await page.route('**/api/meeting-rooms/display', route => route.fulfill({ status: 503, json: {} }))
    await page.goto('/?version=v3')
    const old = await page.locator('meta[name="roombeacon-release"]').getAttribute('content')
    let navigation = 0
    page.on('request', request => { if (request.isNavigationRequest() && request.frame() === page.mainFrame()) navigation++ })
    await page.route('http://127.0.0.1:4178/', async route => {
      const response = await route.fetch()
      const body = (await response.text()).replace(`content="${old}"`, 'content="release-test-next"')
      await route.fulfill({ response, body })
    })
    await page.route('**/assets/*.js', async route => {
      if (route.request().method() === 'HEAD' && !ready) await route.fulfill({ status: 404 })
      else await route.continue()
    })
    await page.clock.runFor(301000)
    if (ready) {
      await expect.poll(() => navigation).toBe(1)
      expect(await page.evaluate(() => localStorage.getItem('argus_room_display'))).toBe('fixture')
      await page.clock.runFor(301000)
      expect(navigation).toBe(1)
    } else {
      await expect(page.locator('.door')).toBeVisible()
      expect(navigation).toBe(0)
    }
  })
}
