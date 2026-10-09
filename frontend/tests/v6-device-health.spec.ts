import {test,expect} from '@playwright/test'
import {fixture} from './configuration.fixture'

const healthy={state:'ready',error:'',age_seconds:12,page_release:'test-release-52',webview:'125.0.6422.165',terminal_state:'free',light_state:'ok'}

test('management heartbeat and applied configuration do not disguise a page or light fault, and recovery clears the fault',async({page})=>{
 const state=await fixture(page)
 Object.assign(state.devices[0],{page_health:{...healthy,state:'failed',error:'renderer',terminal_state:'unknown',light_state:'failed'}})
 await page.goto('/control')
 const row=page.locator('tbody tr').first()
 await expect(row).toContainText('当前配置已应用')
 await expect(row).toContainText('页面运行异常')
 await expect(row).toContainText('灯控异常')
 await expect(page.getByText('管理在线',{exact:true})).toBeVisible()
 await row.getByRole('button',{name:'配置与部署'}).click()
 const panel=page.getByRole('dialog',{name:'设备部署'})
 const health=panel.getByTestId('device-health')
 await expect(health).toContainText('网页渲染进程异常')
 await expect(health).toContainText('test-release-52')
 await expect(health).toContainText('125.0.6422.165')
 await expect(health).toContainText('12 秒前')
 await expect(panel).toContainText('期望版本 2 · 已应用 2')
 await panel.getByRole('button',{name:'关闭',exact:true}).click()
 Object.assign(state.devices[0],{page_health:healthy})
 await page.getByRole('button',{name:'刷新状态',exact:true}).click()
 await row.getByRole('button',{name:'配置与部署'}).click()
 await expect(health).toContainText('页面运行正常')
 await expect(health).toContainText('灯控正常')
 await expect(health).not.toContainText('页面运行异常')
 await expect(health).not.toContainText('网页渲染进程异常')
})

test('a legacy APK explicitly remains unreported, including an old backend without the health field',async({page})=>{
 const state=await fixture(page)
 Object.assign(state.devices[1],{page_health:{...healthy,state:'unknown',error:'',age_seconds:null,page_release:'',webview:'',terminal_state:'unknown',light_state:'unknown'}})
 await page.goto('/control')
 for(const index of [0,1]){
  const row=page.locator('tbody tr').nth(index)
  await expect(row).toContainText('未上报页面状态，请升级 APK')
  await expect(row).not.toContainText('页面运行正常')
 }
})

for(const [stateName,online,label,light] of [
 ['stale',true,'页面回执已过期','灯控回执已过期'],
 ['offline',false,'设备离线，页面状态未确认','灯控状态未确认']
] as const)test(`${stateName} reports cannot reuse a former successful page or light receipt`,async({page})=>{
 const state=await fixture(page)
 Object.assign(state.devices[0],{online,page_health:{...healthy,state:stateName,age_seconds:180}})
 await page.goto('/control')
 const row=page.locator('tbody tr').first()
 await expect(row).toContainText(label)
 await expect(row).toContainText(light)
 await expect(row).not.toContainText('页面运行正常')
 await expect(row).not.toContainText('灯控正常')
})

test('loaded pages with unknown business data remain awaiting confirmation',async({page})=>{
 const state=await fixture(page)
 Object.assign(state.devices[0],{page_health:{...healthy,terminal_state:'unknown'}})
 await page.goto('/control')
 const row=page.locator('tbody tr').first()
 await expect(row).toContainText('页面已加载 · 数据待确认')
 await expect(row).not.toContainText('页面运行正常')
})

test('failed management refresh cannot leave previous page health displayed as current',async({page})=>{
 const state=await fixture(page)
 Object.assign(state.devices[0],{page_health:healthy})
 await page.goto('/control')
 const row=page.locator('tbody tr').first()
 await expect(row).toContainText('页面运行正常')
 await page.route('**/api/v6/admin/devices',route=>route.fulfill({status:503,json:{code:503}}))
 await page.getByRole('button',{name:'刷新状态',exact:true}).click()
 await expect(page.getByRole('alert')).toContainText('服务暂不可用')
 await expect(row).toContainText('页面回执已过期')
 await expect(row).not.toContainText('页面运行正常')
 await expect(row).not.toContainText('灯控正常')
})

test('installation delivery and field acceptance show live page health independently of old readiness and manual records',async({page})=>{
 const state=await fixture(page)
 Object.assign(state.devices[0],{page_health:{...healthy,state:'failed',error:'network',terminal_state:'unknown'}})
 await page.route('**/api/v6/admin/installation',route=>route.fulfill({json:{code:0,data:{executors:[],releases:[],jobs:[{
  id:'1'.repeat(32),batch_id:'batch',executor_id:'server',release_id:'release',ip:'10.0.1.2',port:5555,serial:'TEST-0',state:'accepted',revision:5,lease_until:0,result:'installed',error:'',device_id:state.devices[0].id,device_code:'ABC234',device_ready:true,acceptance_current:true,acceptance:{location:'测试楼',switch_port:'测试端口'},created_at:1
 }]}}}))
 await page.route('**/api/v6/admin/installation/server',route=>route.fulfill({json:{code:0,data:{probe_ready:true,blocker:'',port:5555,apk_configured:true}}}))
 await page.goto('/control')
 await page.getByRole('button',{name:'首装与交付',exact:true}).click()
 const row=page.locator('.install-records tbody tr').first()
 await expect(row).toContainText('已保存此配置的现场验收')
 await expect(row).toContainText('页面运行异常')
 await expect(row).not.toContainText('页面运行正常')
 await row.getByRole('button',{name:'现场验收',exact:true}).click()
 const health=page.getByRole('dialog',{name:'现场交付验收'}).getByTestId('device-health')
 await expect(health).toContainText('页面运行异常')
 await expect(health).toContainText('网页连接失败')
})
