import {test,expect,type Page} from '@playwright/test'
const config={device_profile:'generic',language:'zh-CN',theme_mode:'auto',version:'v6',portrait:false,room_light:false,node_id:'central',reload:0}
const rooms=[
 {room_id:'omm_beijing',name:'同名会议室',region:'北京',location:'公司 / 中国 / 北京 / A座 / 2层 / 东区'},
 {room_id:'omm_shanghai',name:'同名会议室',region:'上海',location:'公司 / 中国 / 上海 / A座 / 2层'},
 {room_id:'omm_other',name:'其他会议室',region:'北京',location:'公司 / 中国 / 北京 / B座 / 3层'},
]
async function setup(page:Page,role='admin'){
 const state={templates:[{id:'template1',name:'横版模板',revision:1,config:{...config}}],writes:[] as any[]}
 const devices=rooms.map((room,i)=>({id:String(i),code:['ABC234','DEF567','GHJ890'][i],status:'active',room_id:room.room_id,
  revision:2,reported_revision:2,online:true,config:{...config},metadata:{model:'RK3568'},error:''}))
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname,method=route.request().method()
  const ok=(data:unknown)=>route.fulfill({json:{code:0,data}})
  if(path.endsWith('/auth/options'))return ok({feishu:true})
  if(path.endsWith('/auth/me'))return ok({subject:'user',role,name:'测试用户',csrf:'csrf'})
  if(path.endsWith('/admin/device-profiles'))return ok([{id:'generic',name:'通用屏幕',model:'',firmware:'',pins:null,active_level:null},{id:'bx68',name:'BX68',model:'RK3568',firmware:'test',pins:{red:148,green:154,blue:147},active_level:0}])
  if(path.endsWith('/admin/devices'))return ok(devices)
  if(path==='/api/room-control/rooms')return ok(rooms)
  if(path.includes('/admin/templates')){
   if(method==='GET')return ok(state.templates)
   const body=route.request().postDataJSON();state.writes.push({method,path,body})
   if(method==='POST')state.templates.push({...body,id:'template2',revision:1})
   else state.templates[0]={...body,id:'template1',revision:2}
   return ok(state.templates.at(-1))
  }
  if(method==='PUT'||path.endsWith('/batch-config')){state.writes.push(route.request().postDataJSON());return ok({})}
  return ok([])
 });return state
}
test('台账地区和位置搜索，绑定支持任意深度级联并清理下级筛选',async({page})=>{
 await setup(page);await page.goto('/control')
 await page.getByLabel('地区 / 园区',{exact:true}).selectOption('北京')
 await expect(page.locator('tbody tr')).toHaveCount(2)
 await page.getByLabel('搜索设备').fill('东区');await expect(page.locator('tbody tr')).toHaveCount(1)
 await page.getByRole('button',{name:'配置',exact:true}).click()
 const panel=page.getByRole('dialog')
 await expect(panel.getByLabel('屏幕方向',{exact:true})).toHaveCount(0)
 await panel.getByLabel('地区 / 园区',{exact:true}).selectOption('北京')
 for(const [i,value] of ['公司','中国','北京','A座','2层','东区'].entries())await panel.getByLabel(`位置第 ${i+1} 级`,{exact:true}).selectOption(value)
 await expect(panel.getByLabel('分配会议室').locator('option')).toHaveCount(2)
 await panel.getByLabel('位置第 4 级',{exact:true}).selectOption('B座')
 await expect(panel.getByLabel('位置第 6 级',{exact:true})).toHaveCount(0)
 await expect(panel.getByLabel('分配会议室')).toHaveValue('')
 await panel.getByLabel('位置第 5 级',{exact:true}).selectOption('3层')
 await panel.getByLabel('分配会议室').selectOption('omm_other')
 await panel.getByLabel('地区 / 园区',{exact:true}).selectOption('上海')
 await expect(panel.getByLabel('分配会议室')).toHaveValue('')
 await expect(panel.getByLabel('位置第 2 级',{exact:true})).toHaveCount(0)
 await panel.getByLabel('分配会议室').selectOption('omm_shanghai')
 await panel.getByLabel('会议室关键词',{exact:true}).fill('不存在')
 await expect(panel.getByLabel('分配会议室')).toHaveValue('')
})
test('模板新建和编辑独立于批量选择，保存不自动下发',async({page})=>{
 const state=await setup(page);await page.goto('/control')
 await page.getByRole('button',{name:'配置模板',exact:true}).click()
 await page.getByRole('button',{name:'新建模板',exact:true}).click()
 await page.getByLabel('模板名称',{exact:true}).fill('竖版模板')
 await page.getByLabel('屏幕方向',{exact:true}).selectOption('true')
 await page.getByRole('button',{name:'保存模板',exact:true}).click()
 await expect(page.getByRole('status')).toContainText('模板已保存')
 expect(state.writes).toHaveLength(1);expect(state.writes[0].method).toBe('POST')
 expect(state.writes[0].body.config.portrait).toBe(true)
 await page.getByRole('article').filter({hasText:'横版模板'}).getByRole('button',{name:'编辑',exact:true}).click()
 await page.getByLabel('模板名称',{exact:true}).fill('修改后的模板')
 await page.getByRole('button',{name:'保存模板',exact:true}).click()
 await expect(page.getByRole('article').filter({hasText:'修改后的模板'})).toBeVisible()
 expect(state.writes[1].method).toBe('PUT');expect(state.writes[1].body.expected_revision).toBe(1)
 await page.screenshot({path:'/tmp/roombeacon-templates.png',fullPage:true})
})
test('只读账号只能查看模板，筛选结果为空有明确提示',async({page})=>{
 await setup(page,'viewer');await page.goto('/control')
 await page.getByLabel('搜索设备').fill('不存在')
 await expect(page.getByText('没有匹配的设备',{exact:true})).toBeVisible()
 await page.getByRole('button',{name:'配置模板',exact:true}).click()
 await expect(page.getByRole('button',{name:'新建模板',exact:true})).toHaveCount(0)
 await expect(page.getByRole('button',{name:'编辑',exact:true})).toHaveCount(0)
})

test('单台下发保留选择时的模板版本，刷新后编辑冲突不丢失草稿',async({page})=>{
 const state=await setup(page);await page.goto('/control')
 await page.getByRole('button',{name:'配置',exact:true}).first().click()
 await page.getByLabel('硬件安装模板',{exact:true}).selectOption('template1')
 state.templates[0].revision=2;state.templates[0].config.portrait=true
 await page.getByRole('button',{name:'刷新状态',exact:true}).evaluate((el:HTMLElement)=>el.click())
 await page.getByRole('button',{name:'保存并下发'}).click()
 await expect.poll(()=>state.writes.length).toBe(1)
 expect(state.writes[0].template_revision).toBe(1)
 expect(state.writes[0].config.portrait).toBe(false)
 await page.getByRole('button',{name:'配置模板',exact:true}).click()
 await page.getByRole('article').filter({hasText:'横版模板'}).getByRole('button',{name:'编辑',exact:true}).click()
 await page.getByLabel('模板名称',{exact:true}).fill('保留的编辑')
 await page.route('**/api/v6/admin/templates/template1',route=>route.fulfill({status:409,json:{code:409}}))
 await page.getByRole('button',{name:'保存模板',exact:true}).click()
 await expect(page.getByRole('alert')).toContainText('配置已变化')
 await expect(page.getByLabel('模板名称',{exact:true})).toHaveValue('保留的编辑')
})

test('切换地区清理不可见的批量选择，会议室列表共享地区筛选',async({page})=>{
 await setup(page);await page.goto('/control')
 await page.getByLabel('选择 ABC234',{exact:true}).check()
 await page.getByLabel('地区 / 园区',{exact:true}).selectOption('上海')
 await expect(page.locator('.v6-batch')).toHaveCount(0)
 await page.getByRole('button',{name:'会议室',exact:true}).click()
 await expect(page.locator('.v6-room-grid article')).toHaveCount(1)
 await expect(page.locator('.v6-room-grid')).toContainText('上海')
 await expect(page.getByRole('button',{name:'业务方案',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'配置模板',exact:true}).click()
 await page.getByRole('button',{name:'新建模板',exact:true}).click()
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})

test('会议室业务方案独立保存，不修改设备或模板',async({page})=>{
 const state=await setup(page),updates:any[]=[]
 const policy={owner:'official',mode:'off',early_minutes:10,grace_minutes:10,release_delay_seconds:60,native_policy_cleared:false,release_verified:false,revision:'policy1'}
 await page.route('**/api/room-control/usage/omm_beijing**',route=>{
  if(route.request().method()==='PUT'){
   expect(route.request().headers()['x-rb-csrf']).toBe('csrf')
   updates.push(route.request().postDataJSON())
  }
  return route.fulfill({json:{data:{usage:{policy,paused:true,record:null},audit:[],global_audit:[],writes_enabled:false}}})
 })
 await page.goto('/control');await page.getByRole('button',{name:'会议室',exact:true}).click()
 await page.locator('.v6-room-grid article').filter({hasText:'东区'}).getByRole('button',{name:'业务方案'}).click()
 await expect(page.getByRole('dialog',{name:'会议室业务方案'})).toBeVisible()
 await page.getByLabel('签到方案').selectOption('v5')
 await page.getByRole('button',{name:'保存房间规则'}).click()
 await expect.poll(()=>updates.length).toBe(1)
 expect(updates[0].owner).toBe('v5');expect(state.writes).toHaveLength(0)
})
