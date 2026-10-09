import {test,expect} from '@playwright/test'
import {fixture} from './configuration.fixture'

test('删除设备需二次确认，取消不写入，确认后从台账移除',async({page})=>{
 const state=await fixture(page);state.devices[0].code='W9TW7S'
 await page.route('**/api/v6/admin/devices/'+state.devices[0].id,async route=>{
  expect(route.request().method()).toBe('DELETE')
  expect(route.request().headers()['x-rb-csrf']).toBe('csrf')
  const body=route.request().postDataJSON();expect(body).toEqual({expected_revision:2,confirm_code:'W9TW7S'})
  state.writes.push({path:new URL(route.request().url()).pathname,body});state.devices.shift()
  return route.fulfill({json:{code:0,data:{deleted:true}}})
 })
 await page.goto('/control');await page.getByRole('button',{name:'删除设备 W9TW7S'}).click()
 const dialog=page.getByRole('dialog',{name:'确认删除设备'});await expect(dialog).toContainText('W9T W7S');await expect(dialog).toContainText('同名会议室')
 await page.screenshot({path:'/tmp/roombeacon-delete-confirmation.png',fullPage:true})
 await dialog.getByRole('button',{name:'保留设备'}).click();expect(state.writes).toHaveLength(0)
 await page.getByRole('button',{name:'删除设备 W9TW7S'}).click();await dialog.getByRole('button',{name:'确认删除',exact:true}).click()
 await expect(dialog).toHaveCount(0);await expect(page.locator('tbody tr')).toHaveCount(2);await expect(page.getByRole('status')).toContainText('旧凭证已失效')
})

test('只读账号没有删除入口',async({page})=>{
 await fixture(page,'viewer');await page.goto('/control');await expect(page.locator('tbody tr')).toHaveCount(3)
 await expect(page.getByRole('button',{name:/删除设备/})).toHaveCount(0)
 await page.getByRole('button',{name:'查看',exact:true}).first().click();await expect(page.getByRole('button',{name:/删除/})).toHaveCount(0)
})

test('删除版本冲突保留确认框和设备，等待用户重新核对',async({page})=>{
 const state=await fixture(page);state.conflict=true;await page.goto('/control');await page.getByRole('button',{name:'删除设备 ABC234'}).click()
 const dialog=page.getByRole('dialog',{name:'确认删除设备'});await dialog.getByRole('button',{name:'确认删除',exact:true}).click()
 await expect(dialog.getByRole('alert')).toContainText('配置已变化');await expect(page.locator('tbody tr')).toHaveCount(3)
})

test('日常模板只显示两个硬件与两个软件，历史仍可查阅',async({page})=>{
 const state=await fixture(page)
 const copy=(id:string,name:string,source=state.catalog[0])=>({...structuredClone(source),id,name})
 state.catalog[0].name='BX68 · 13.3 寸 · 1920×1080 · 横屏';state.catalog[1].name='签到版'
 state.catalog.push(copy('hw-old','RK3568_R · 10.1 寸 · 1280×800 · 横屏'),
  {...copy('sw-display','未签到版',state.catalog[1]),spec:{...state.catalog[1].spec,roombeacon_checkin:false}},
  {...copy('hw-duplicate','重复 BX68'),retired:true},{...copy('hw-generic','通用屏幕'),retired:true},
  {...copy('sw-old','旧测试签到软件',state.catalog[1]),retired:true})
 await page.goto('/control');await page.getByRole('button',{name:'配置与部署',exact:true}).first().click()
 const panel=page.getByRole('dialog');await expect(panel.getByLabel('硬件安装模板',{exact:true}).locator('option')).toHaveCount(3)
 await expect(panel.getByLabel('软件模板',{exact:true}).locator('option')).toHaveCount(3)
 await panel.getByRole('button',{name:'关闭',exact:true}).click();await page.getByRole('button',{name:'硬件安装模板',exact:true}).click()
 await expect(page.locator('.v6-template-grid:visible > article')).toHaveCount(2);await page.locator('.v6-presets:visible').getByLabel('包含历史与已归档').check();await expect(page.locator('.v6-template-grid:visible > article')).toHaveCount(4)
})

test('未签到版保留飞书二维码，不启用 RoomBeacon 签到或保活',async({page})=>{
 const now=Date.now();const calls:string[]=[]
 await page.route('**/api/**',route=>{
  calls.push(new URL(route.request().url()).pathname)
  return route.fulfill({json:{data:{room:{room_id:'omm_test',name:'测试会议室',capacity:12,enabled:true},events:[],
   synced_at:new Date(now).toISOString(),server_time:new Date(now).toISOString(),valid_until:new Date(now+60000).toISOString(),
   usage_owner:'official',checkin_qr:'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"/>',
   display_preferences:{display_version:'v7',roombeacon_checkin:false,theme_mode:'light',language:'zh-CN'}}}})
 })
 await page.goto('/?managed=1&version=v6');await expect(page.getByText('测试会议室',{exact:true})).toBeVisible()
 await expect(page.locator('.checkin-card')).toHaveCount(1)
 await expect(page.getByText('飞书扫码签到',{exact:true})).toBeVisible()
 await expect(page.locator('.room-usage,.v7-checkin')).toHaveCount(0)
 await expect(page.getByRole('button',{name:'签到',exact:true})).toHaveCount(0)
 expect(calls.some(path=>path.includes('/usage'))).toBe(false)
})
