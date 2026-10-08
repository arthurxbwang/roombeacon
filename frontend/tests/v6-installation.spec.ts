import {test,expect,type Page} from '@playwright/test'
import {fixture} from './configuration.fixture'
import type {InstallJob,InstallOverview} from '../src/api/installation'

const base='/api/v6/admin/installation'
const manifest={package:'com.roombeacon.shell',version_code:10,version_name:'0.7.0',sha256:'a'.repeat(64),certificate_sha256:'b'.repeat(64),size:1234,models:['BX68']}
async function setup(page:Page,role='admin'){
 const original=await fixture(page,role)
 const state={value:{executors:[{id:'e'.repeat(32),name:'现场电脑',revoked:0,expires:Date.now()/1000+86400,last_seen:0}],releases:[{id:'f'.repeat(32),manifest,created_at:1}],jobs:[]} as InstallOverview,writes:[] as {path:string;body:any}[],fail:false,reads:0}
 await page.route('**/api/v6/admin/installation**',async route=>{
  const path=new URL(route.request().url()).pathname,ok=(data:unknown)=>route.fulfill({json:{code:0,data}})
  if(path.endsWith('/server'))return ok({probe_ready:true,blocker:'',port:5555,apk_configured:true})
  if(route.request().method()==='GET'){state.reads++;return ok(state.value)}
  expect(route.request().headers()['x-rb-csrf']).toBe('csrf')
  const body=route.request().postDataJSON();state.writes.push({path,body})
  if(state.fail)return route.fulfill({status:409,json:{code:409,message:'目标已有待核实任务，请先处理原任务'}})
  if(path.endsWith('/batches')){
   state.value.jobs.push({id:'1'.repeat(32),batch_id:body.request_id,executor_id:body.executor_id,release_id:body.release_id,...body.targets[0],state:'queued',revision:1,lease_until:0,result:'',error:'',device_id:'',device_code:'',device_ready:false,acceptance_current:false,acceptance:{},created_at:1})
   return ok({batch_id:body.request_id})
  }
  if(path.endsWith('/associate')){const job=state.value.jobs[0];Object.assign(job,{state:'associated',revision:4,device_id:original.devices[0].id,device_code:'ABC234',device_ready:true});return ok({})}
  if(path.endsWith('/accept')){Object.assign(state.value.jobs[0],{state:'accepted',revision:5,acceptance_current:true,acceptance:body});return ok({})}
  if(path.endsWith('/executors'))return ok({id:'new',token:'rbi:test-one-time-credential'})
  return ok({})
 })
 await page.goto('/control');await page.getByRole('button',{name:'首装与交付',exact:true}).click()
 await expect(page.getByRole('heading',{name:'首装与交付'})).toBeVisible()
 return state
}
function installedJob():InstallJob{return {id:'1'.repeat(32),batch_id:'batch',executor_id:'e'.repeat(32),release_id:'f'.repeat(32),ip:'10.0.1.2',port:5555,serial:'TEST-0',state:'installed',revision:3,lease_until:0,result:'installed',error:'',device_id:'',device_code:'',device_ready:false,acceptance_current:false,acceptance:{},created_at:1}}

test('installation scope preview, idempotent retry and persisted task list',async({page})=>{
 const state=await setup(page)
 await page.getByText('高级设置与现场助手',{exact:true}).click()
 await page.getByLabel('现场助手',{exact:true}).selectOption('e'.repeat(32))
 await page.getByLabel('正式 APK',{exact:true}).selectOption('f'.repeat(32))
 await page.getByLabel('设备清单').fill('10.0.1.2 TEST-0 5555')
 await page.getByRole('button',{name:'检查安装范围'}).click()
 await expect(page.getByRole('heading',{name:'确认安装 1 台'})).toBeVisible()
 expect(state.writes).toHaveLength(0)
 state.fail=true
 await page.getByRole('button',{name:'确认创建安装任务'}).click()
 await expect(page.getByRole('alert').filter({hasText:'目标已有待核实任务'})).toBeVisible()
 state.fail=false
 await page.getByRole('button',{name:'确认创建安装任务'}).click()
 await expect(page.getByText('等待助手领取',{exact:true})).toBeVisible()
 expect(state.writes[0].body.request_id).toBe(state.writes[1].body.request_id)
 await page.reload();await page.getByRole('button',{name:'首装与交付',exact:true}).click()
 await expect(page.getByText('等待助手领取',{exact:true})).toBeVisible()
 await page.screenshot({path:'/tmp/roombeacon-installation-ui.png',fullPage:true})
})

test('association, existing room configuration and explicit field acceptance',async({page})=>{
 const state=await setup(page);state.value.jobs=[installedJob()]
 await page.getByRole('button',{name:'刷新安装任务'}).click()
 await page.getByRole('button',{name:'关联屏幕短码'}).click()
 const dialog=page.getByRole('dialog',{name:'关联屏幕短码'})
 await dialog.getByLabel('屏幕六位短码').fill('ABC234')
 await expect(dialog.getByRole('button',{name:'确认设备关联'})).toBeDisabled()
 await dialog.getByRole('checkbox').check();await dialog.getByRole('button',{name:'确认设备关联'}).click()
 await expect(page.getByText('已关联，等待配置与验收',{exact:true})).toBeVisible()
 await page.getByRole('button',{name:'房间配置',exact:true}).click()
 await expect(page.getByRole('dialog')).toBeVisible()
 await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click()
 await page.getByRole('button',{name:'现场验收',exact:true}).click()
 const acceptance=page.getByRole('dialog',{name:'现场交付验收'})
 await acceptance.getByLabel('安装位置').fill('测试楼 2 层')
 await acceptance.getByLabel('交换机与物理端口').fill('测试交换机 / 端口 5')
 await expect(acceptance.getByRole('button',{name:'保存现场验收记录'})).toBeDisabled()
 for(const check of await acceptance.getByRole('checkbox').all())await check.check()
 await acceptance.getByRole('button',{name:'保存现场验收记录'}).click()
 await expect(page.getByText('已保存此配置的现场验收',{exact:true})).toBeVisible()
 expect(state.writes.at(-1)?.body.device_revision).toBe(2)
 expect(state.writes.at(-1)?.body.poe_recovery_adb_stays_closed).toBe(true)
})

test('viewer can read but cannot create, associate or accept',async({page})=>{
 const state=await setup(page,'viewer');state.value.jobs=[installedJob()]
 await page.getByRole('button',{name:'刷新安装任务'}).click()
 await expect(page.getByText('安装完成，等待关联',{exact:true})).toBeVisible()
 await expect(page.getByRole('button',{name:'关联屏幕短码'})).toHaveCount(0)
 await expect(page.getByRole('button',{name:'检查安装范围'})).toHaveCount(0)
 await expect(page.getByText('登记现场助手',{exact:false})).toHaveCount(0)
 expect(state.writes).toHaveLength(0)
})

test('uncertain tasks require field acknowledgement; one-time credential cleared on leaving',async({page})=>{
 const state=await setup(page);state.value.jobs=[{...installedJob(),state:'uncertain'}]
 await page.getByRole('button',{name:'刷新安装任务'}).click()
 await page.getByRole('button',{name:'核实后重试'}).click()
 const dialog=page.getByRole('dialog',{name:'核实安装结果'})
 await expect(dialog.getByRole('button',{name:'确认重试'})).toBeDisabled()
 await dialog.getByRole('checkbox').check();await dialog.getByRole('button',{name:'确认重试'}).click()
 expect(state.writes.at(-1)?.body.previous_executor_stopped).toBe(true)
 await page.getByText('高级设置与现场助手',{exact:true}).click()
 await page.getByText('1. 登记现场助手',{exact:true}).click()
 await page.getByLabel('电脑名称').fill('交付电脑')
 await page.getByRole('button',{name:'生成一天有效的助手凭证'}).click()
 await expect(page.getByText('rbi:test-one-time-credential',{exact:true})).toBeVisible()
 await page.getByRole('button',{name:'设备台账',exact:true}).click()
 const reads=state.reads;await page.waitForTimeout(1100);expect(state.reads).toBe(reads)
 await page.getByRole('button',{name:'首装与交付',exact:true}).click()
 await expect(page.getByText('rbi:test-one-time-credential',{exact:true})).toHaveCount(0)
})

async function quickProbe(page:Page,overrides:Record<string,unknown>={}){
 const state=await setup(page)
 await page.route('**/api/v6/admin/installation/probe',async route=>{
  expect(route.request().headers()['x-rb-csrf']).toBe('csrf')
  state.writes.push({path:'/probe',body:route.request().postDataJSON()})
  return route.fulfill({json:{code:0,data:{id:'a'.repeat(32),ip:'10.0.1.2',port:5555,serial:'TEST-0',model:'BX68',android:'11',existing:false,manifest,can_initialize:true,blocker:'',expires:Date.now()/1000+300,...overrides}}})
 })
 await page.getByLabel('设备 IP',{exact:true}).fill('10.0.1.2')
 await page.getByRole('button',{name:'检测设备',exact:true}).click()
 await expect(page.getByRole('heading',{name:'已连接到设备'})).toBeVisible()
 return state
}

test('IP check reveals identity, initializes only on confirmation and keeps advanced setup hidden',async({page})=>{
 const state=await quickProbe(page)
 await expect(page.getByLabel('电脑名称')).not.toBeVisible()
 await expect(page.getByLabel('APK 清单 JSON')).not.toBeVisible()
 expect(state.writes).toEqual([{path:'/probe',body:{ip:'10.0.1.2',port:5555}}])
 await page.getByRole('button',{name:'确认初始化',exact:true}).click()
 await expect(page.getByRole('status').filter({hasText:'初始化任务已提交'})).toBeVisible()
 expect(state.writes.at(-1)?.path).toBe(base+'/initialize')
 expect(state.writes.at(-1)?.body).toEqual({probe_id:'a'.repeat(32),confirmed:true})
})

test('changing IP invalidates probe; missing APK and expired probes cannot initialize',async({page})=>{
 const state=await quickProbe(page)
 await page.getByLabel('设备 IP',{exact:true}).fill('10.0.1.3')
 await expect(page.getByRole('button',{name:'确认初始化',exact:true})).toHaveCount(0)
 expect(state.writes).toHaveLength(1)
 await page.unroute('**/api/v6/admin/installation/probe')
 await page.route('**/api/v6/admin/installation/probe',route=>route.fulfill({json:{code:0,data:{id:'a'.repeat(32),ip:'10.0.1.3',serial:'TEST-1',model:'BX68',android:'11',can_initialize:false,blocker:'尚未配置默认正式 APK',expires:0}}}))
 await page.getByRole('button',{name:'检测设备',exact:true}).click()
 await expect(page.getByRole('status').filter({hasText:'尚未配置默认正式 APK'})).toBeVisible()
 await expect(page.getByRole('button',{name:'确认初始化',exact:true})).toHaveCount(0)
})

test('probe expires before confirmation and failures allow another check',async({page})=>{
 await quickProbe(page,{expires:1})
 await expect(page.getByRole('button',{name:'确认初始化',exact:true})).toBeDisabled()
 await expect(page.getByText('检测结果已过期，请重新检测设备。')).toBeVisible()
 await page.unroute('**/api/v6/admin/installation/probe')
 await page.route('**/api/v6/admin/installation/probe',route=>route.fulfill({status:409,json:{code:409,message:'设备尚未授权 ADB，请在设备上允许调试后重新检测'}}))
 await page.getByRole('button',{name:'检测设备',exact:true}).click()
 await expect(page.getByRole('alert').filter({hasText:'尚未授权 ADB'})).toBeVisible()
 await expect(page.getByRole('button',{name:'检测设备',exact:true})).toBeEnabled()
 await expect(page.getByRole('button',{name:'确认初始化',exact:true})).toHaveCount(0)
})

for(const width of [1440,390])test(`installation layout keeps aligned padding and contains expanded settings at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:1000});await setup(page)
 const card=page.locator('.installation'),heading=page.getByRole('heading',{name:'首装与交付',exact:true})
 const input=page.getByLabel('设备 IP',{exact:true}),advanced=card.locator('details.advanced')
 const records=page.getByRole('heading',{name:'安装任务与交付记录'})
 const bounds=await card.boundingBox(),title=await heading.boundingBox()
 expect(title!.x-bounds!.x).toBeGreaterThanOrEqual(16)
 for(const item of [input,advanced,records]){
  const box=await item.boundingBox();expect(Math.abs(box!.x-title!.x)).toBeLessThanOrEqual(1)
  expect(box!.x+box!.width).toBeLessThanOrEqual(bounds!.x+bounds!.width-16)
 }
 const fold=await advanced.boundingBox()
 expect(Math.abs(fold!.width-(bounds!.width-2*(title!.x-bounds!.x)))).toBeLessThanOrEqual(2)
 const refresh=await page.getByRole('button',{name:'刷新安装任务'}).boundingBox()
 expect(refresh!.height).toBeLessThanOrEqual(48)
 await page.getByText('高级设置与现场助手',{exact:true}).click()
 await page.getByText('1. 登记现场助手',{exact:true}).click()
 await page.getByText('2. 登记已批准的正式 APK',{exact:true}).click()
 for(const item of [page.getByLabel('电脑名称'),page.getByLabel('APK 清单 JSON')]){
  const box=await item.boundingBox();expect(box!.x).toBeGreaterThan(title!.x)
  expect(box!.x+box!.width).toBeLessThan(bounds!.x+bounds!.width-16)
 }
 expect(await card.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true)
 await page.screenshot({path:`/tmp/installation-layout-${width}-expanded.png`,fullPage:true})
 await page.getByText('高级设置与现场助手',{exact:true}).click()
 await page.screenshot({path:`/tmp/installation-layout-${width}.png`,fullPage:true})
})

test('missing backend APK is visible before probing and does not send user to field setup',async({page})=>{
 await setup(page)
 await page.route('**/api/v6/admin/installation/server',route=>route.fulfill({json:{code:0,data:{probe_ready:true,blocker:'',port:5555,apk_configured:false}}}))
 await page.getByRole('button',{name:'设备台账',exact:true}).click()
 await page.getByRole('button',{name:'首装与交付',exact:true}).click()
 await expect(page.getByRole('alert').filter({hasText:'后台尚未准备默认安装包'})).toBeVisible()
 await page.getByLabel('设备 IP',{exact:true}).fill('10.0.1.2')
 await expect(page.getByRole('button',{name:'检测设备',exact:true})).toBeEnabled()
 await page.getByText('高级设置与现场助手',{exact:true}).click()
 await expect(page.getByText('后台已能连接设备时，无需登记现场助手。',{exact:true})).toBeVisible()
})
