import {test,expect} from '@playwright/test'
const now='2026-09-22T12:00:00Z'
const sample={room:{room_id:'omm_test',name:'测试会议室',capacity:12,enabled:true},events:[],synced_at:now,server_time:now,valid_until:'2026-09-22T12:05:00Z',titles_available:true,
 daylight:{city:'北京',timezone:'Asia/Shanghai',windows:[{start:'2026-09-22T00:00:00Z',end:'2026-09-22T10:00:00Z'}],valid_until:'2026-09-23T00:00:00Z'}}
test('始终白天在夜间生效，英文门牌断网仍是未知',async({page})=>{
 await page.clock.install();let fail=false
 await page.route('**/api/meeting-rooms/display',route=>fail?route.fulfill({status:503,json:{code:503}}):route.fulfill({json:{data:{...sample,display_preferences:{theme_mode:'light',language:'en'}}}}))
 await page.goto('/?managed=1&version=v6');await expect(page.locator('main')).toHaveClass(/theme-light/);await expect(page.locator('main')).toHaveAttribute('lang','en')
 await expect(page.getByText('Available',{exact:true}).first()).toBeVisible();await expect(page.getByText('Upcoming meetings',{exact:true})).toBeVisible()
 await page.setViewportSize({width:1280,height:720});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'/tmp/roombeacon-english-day.png'})
 fail=true;await page.clock.fastForward(16000);await expect(page.getByText('Status unavailable',{exact:true})).toBeVisible();await expect(page.locator('main')).toHaveAttribute('data-terminal-state','unknown');await expect(page.locator('main')).toHaveClass(/theme-light/)
})
test('自动昼夜按城市窗口切换，缺少城市时白天兜底',async({page})=>{
 await page.clock.install();let mode='night'
 await page.route('**/api/meeting-rooms/display',route=>route.fulfill({json:{data:{...sample,daylight:mode==='missing'?null:{...sample.daylight,windows:mode==='day'?[{start:'2026-09-22T00:00:00Z',end:'2026-09-22T23:00:00Z'}]:sample.daylight.windows},display_preferences:{theme_mode:'auto',language:'zh-CN'}}}}))
 await page.goto('/?managed=1&version=v6');await expect(page.locator('main')).toHaveClass(/theme-dark/)
 mode='day';await page.clock.fastForward(16000);await expect(page.locator('main')).toHaveClass(/theme-light/)
 mode='missing';await page.clock.fastForward(16000);await expect(page.locator('main')).toHaveClass(/theme-light/);await expect(page.getByText('城市待配置')).toBeVisible()
})
test('英文官方签到和 V5 异常状态正确显示',async({page})=>{
 let v5=false
 await page.route('**/api/meeting-rooms/display',route=>route.fulfill({json:{data:{...sample,usage_owner:v5?'v5':'official',checkin_qr:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"/>',display_preferences:{theme_mode:'light',language:'en'}}}}))
 await page.route('**/api/meeting-rooms/usage',route=>route.fulfill({status:503,json:{code:503}}))
 await page.goto('/?managed=1&version=v6');await expect(page.getByText('Scan to check in',{exact:true})).toBeVisible()
 v5=true;await page.reload();await expect(page.getByText('Awaiting check-in status')).toBeVisible();await expect(page.getByText('V5 not enabled; schedule display remains available')).toBeVisible();await expect(page.getByRole('button',{name:'Check in',exact:true})).toHaveCount(0)
})
test('新版原生入口冷启动遇到缓存故障，仍保留白天和语言配置',async({page})=>{
 await page.route('**/api/meeting-rooms/display',route=>route.fulfill({status:503,json:{code:503}}))
 await page.goto('/?managed=1&version=v6&theme=light&lang=en')
 await expect(page.locator('main')).toHaveClass(/theme-light/)
 await expect(page.locator('main')).toHaveAttribute('lang','en')
 await expect(page.getByText('Sync failed; retrying')).toBeVisible()
 await expect(page.locator('main')).toHaveAttribute('data-terminal-state','unknown')
})
