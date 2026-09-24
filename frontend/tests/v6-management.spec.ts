import {test,expect,type Page} from '@playwright/test'
const profiles=[{id:'generic',name:'通用屏幕（无灯控）',model:'',firmware:'',pins:null,active_level:null},{id:'bx68',name:'BX68 · 13.3 寸 1080P',model:'RK3568',firmware:'RK3568_BX68_Android 11_64-20260331.094925_ZX-keys',pins:{red:148,green:154,blue:147},active_level:0},{id:'rk3568_r',name:'RK3568_R · 1280×800',model:'rk3568_r',firmware:'rk3568-11.0-20230426.150223',pins:{red:154,green:148,blue:147},active_level:1}]
const config={version:'v6',portrait:false,room_light:true,node_id:'central',reload:0}
const sample={id:'a'.repeat(32),code:'ABC234',status:'pending',room_id:'',revision:1,reported_revision:1,online:true,last_seen:1900000000,error:'',config,
  metadata:{model:'测试样机 BX68',serial:'TEST-SN-001',apk:'0.6.0',android:'11',network:'ethernet',light_supported:true,interfaces:[{name:'eth0',mac:'02:00:00:00:00:01',addresses:['192.0.2.10']}]}}
async function fixture(page:Page,role='admin',logged=true){
 const state={logged,device:structuredClone(sample),saved:[] as any[],templates:[] as any[],batches:[] as any[]}
 await page.route('**/api/**',async route=>{
  const p=new URL(route.request().url()).pathname,method=route.request().method(),ok=(data:unknown)=>route.fulfill({json:{code:0,data}})
  if(p==='/api/v6/auth/options')return ok({feishu:true})
  if(p==='/api/v6/auth/session'){state.logged=true;return ok({authenticated:true})}
  if(p==='/api/v6/auth/me')return state.logged?(role==='pending'?route.fulfill({status:403,json:{code:403}}):ok({subject:'u',name:'测试管理员',role,csrf:'test-csrf'})):route.fulfill({status:401,json:{code:401}})
  if(p==='/api/v6/auth/logout'){state.logged=false;return ok({})}
  if(p==='/api/v6/admin/devices')return ok([state.device])
  if(p==='/api/room-control/rooms')return ok([{room_id:'omm_test',name:'测试会议室',region:'北京',location:'2F'}])
  if(p==='/api/v6/admin/device-profiles')return ok(profiles)
  if(p==='/api/v6/admin/templates'){if(method==='POST'){state.templates.push({revision:1,id:String(state.templates.length+1),...route.request().postDataJSON()});return ok({})}return ok(state.templates)}
  if(p==='/api/v6/admin/batch-config'){state.batches.push(route.request().postDataJSON());return ok({updated:1})}
  if(p==='/api/v6/admin/audit')return ok([])
  if(p==='/api/v6/auth/users')return ok([{subject:'pending-user',name:'待授权用户',role:'pending'}])
  if(p==='/api/v6/admin/devices/'+sample.id&&method==='PUT'){
   expect(route.request().headers()['x-rb-csrf']).toBe('test-csrf')
   const body=route.request().postDataJSON();state.saved.push(body);state.device={...state.device,...body,revision:2,reported_revision:1};return ok(state.device)
  }
  return route.fulfill({status:404,json:{code:404}})
 });return state
}
test('V6 登录、短码核对与后台激活下发',async({page})=>{
 const state=await fixture(page,'admin',false);await page.goto('/')
 await expect(page).toHaveURL(/\/control$/)
 await expect(page.getByRole('link',{name:'飞书扫码 / 快捷登录'})).toHaveAttribute('href','/api/v6/auth/feishu/start')
 await expect(page.getByLabel('主控凭证')).toHaveCount(0)
 await expect(page.getByRole('button',{name:'退出登录'})).toHaveCount(0)
 await expect(page.getByRole('button',{name:'清除当前登录状态'})).toHaveCount(0)
 await page.route('**/api/v6/auth/feishu/start',async route=>{state.logged=true;await route.fulfill({status:302,headers:{location:'/control'}})})
 await page.getByRole('link',{name:'飞书扫码 / 快捷登录'}).click()
 await expect(page.getByText('ABC 234',{exact:true})).toBeVisible();await expect(page.getByText('有线 / PoE')).toBeVisible()
 await page.getByRole('button',{name:'配置',exact:true}).click()
 await page.getByRole('dialog').getByLabel('设备状态').selectOption('active');await page.getByLabel('分配会议室').selectOption('omm_test')
 await page.getByRole('button',{name:'保存并下发'}).click();await expect(page.getByText('待设备应用',{exact:true})).toBeVisible()
 expect(state.saved[0].expected_revision).toBe(1);expect(state.saved[0].room_id).toBe('omm_test')
 await expect(page.getByRole('dialog')).toHaveCount(0);await page.setViewportSize({width:1440,height:1000})
 await page.screenshot({path:'/tmp/roombeacon-v6-admin-test.png',fullPage:true})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
test('待授权退出会话：失败可重试，成功后隐藏退出入口',async({page})=>{
 const state=await fixture(page,'pending');await page.goto('/control')
 await expect(page.getByRole('alert')).toContainText('等待管理员')
 await page.route('**/api/v6/auth/logout',route=>route.fulfill({status:503,json:{code:503}}))
 await page.getByRole('button',{name:'退出登录',exact:true}).click()
 await expect(page.getByRole('alert')).toContainText('服务暂不可用')
 await expect(page.getByRole('button',{name:'退出登录',exact:true})).toBeVisible();expect(state.logged).toBe(true)
 await page.unroute('**/api/v6/auth/logout')
 const request=page.waitForRequest('**/api/v6/auth/logout')
 await page.getByRole('button',{name:'退出登录',exact:true}).click()
 expect((await request).headers()['x-rb-logout']).toBe('1')
 await expect(page.getByRole('button',{name:'退出登录',exact:true})).toHaveCount(0);expect(state.logged).toBe(false)
 await expect(page.getByRole('link',{name:'飞书扫码 / 快捷登录'})).toBeVisible()
 await page.reload();await expect(page.getByRole('button',{name:'退出登录',exact:true})).toHaveCount(0)
})
for(const role of ['admin','viewer'])test(`后台退出会话：${role}右上角正常退出`,async({page})=>{
 const state=await fixture(page,role);await page.goto('/control')
 await expect(page.locator('header').getByRole('button',{name:'退出登录',exact:true})).toBeVisible()
 await page.locator('header').getByRole('button',{name:'退出登录',exact:true}).click()
 await expect(page.getByRole('heading',{name:'飞书登录会议灯塔'})).toBeVisible()
 await expect(page.getByRole('button',{name:'退出登录',exact:true})).toHaveCount(0);expect(state.logged).toBe(false)
})
test('飞书未授权与失败回调保持登录入口',async({page})=>{
 await fixture(page,'admin',false)
 await page.route('**/api/v6/auth/me',route=>route.fulfill({status:403,json:{code:403}}))
 await page.goto('/control');await expect(page.getByRole('alert')).toContainText('等待管理员')
 await expect(page.getByRole('button',{name:'账号权限'})).toHaveCount(0)
 await page.unroute('**/api/v6/auth/me')
 await page.goto('/control?login_error=feishu');await expect(page.getByRole('alert')).toContainText('飞书登录未完成')
 await expect(page.getByRole('link',{name:'飞书扫码 / 快捷登录'})).toBeVisible()
 await page.screenshot({path:'/tmp/roombeacon-feishu-login.png',fullPage:true})
})
test('企业登录不可用不显示密码入口',async({page})=>{
 await fixture(page,'admin',false)
 await page.route('**/api/v6/auth/options',route=>route.fulfill({json:{code:0,data:{feishu:false}}}))
 await page.goto('/');await expect(page.getByText('飞书登录暂不可用，请联系管理员。')).toBeVisible()
 await expect(page.getByRole('link',{name:'飞书扫码 / 快捷登录'})).toHaveCount(0)
 await expect(page.locator('input[type=password]')).toHaveCount(0)
})
test('只读账号不显示发布与权限操作',async({page})=>{
 await fixture(page,'viewer');await page.goto('/control');await expect(page.getByRole('button',{name:'账号权限'})).toHaveCount(0)
 await page.getByRole('button',{name:'查看',exact:true}).click();await expect(page.getByRole('button',{name:'保存并下发'})).toHaveCount(0)
 await expect(page.getByRole('button',{name:'远程刷新'})).toHaveCount(0);await expect(page.getByLabel('分配会议室')).toBeDisabled()
})
test('短码分组搜索，离线与应用失败不误报成功',async({page})=>{
 const state=await fixture(page);state.device.online=false;state.device.error='应用失败';state.device.reported_revision=0
 await page.goto('/control');await page.getByLabel('搜索设备').fill('ABC 234');await expect(page.getByText('ABC 234',{exact:true})).toBeVisible()
 await expect(page.getByText('应用异常',{exact:true})).toBeVisible();await expect(page.getByText('待激活 · 离线',{exact:true})).toBeVisible()
 await page.getByLabel('搜索设备').fill('no-match');await expect(page.locator('tbody tr')).toHaveCount(0)
})
test('配置冲突保留编辑并提示刷新',async({page})=>{
 await fixture(page);await page.route('**/api/v6/admin/devices/'+sample.id,route=>route.fulfill({status:409,json:{code:409}}))
 await page.goto('/control');await page.getByRole('button',{name:'配置',exact:true}).click();await page.getByRole('button',{name:'保存并下发'}).click()
 await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByRole('alert')).toContainText('配置已变化')
})
test('受管门牌不要求输入凭证，失效后保持未知',async({page})=>{
 await page.route('**/api/meeting-rooms/display',route=>route.fulfill({status:401,json:{code:401}}));await page.goto('/?version=v6&managed=1')
 await expect(page.getByRole('heading',{name:'绑定会议门牌'})).toHaveCount(0);await expect(page.locator('main')).toHaveAttribute('data-terminal-state','unknown')
})

test('型号模板保存接线、语言和昼夜；复制调整不改变批量选择',async({page})=>{
 const state=await fixture(page);state.device.status='active';state.device.room_id='omm_test'
 Object.assign(state.device.metadata,{model:profiles[1].model,firmware:profiles[1].firmware,config_schema:2})
 await page.goto('/control');await page.getByRole('button',{name:'配置模板',exact:true}).click()
 await page.getByRole('button',{name:'新建模板',exact:true}).click();await page.getByLabel('模板名称').fill('BX 白天英文');await expect(page.getByText('低电平点亮 · 高电平熄灭')).toBeVisible()
 await expect(page.locator('.v6-wiring')).toContainText('148')
 await page.getByLabel('自动切换白天／黑夜').uncheck();await page.getByLabel('门牌语言').selectOption('en')
 await expect(page.getByText('已关闭自动切换，始终使用白天模式。')).toBeVisible()
 await page.getByRole('button',{name:'保存模板',exact:true}).click();await expect(page.locator('.v6-template-grid')).toContainText('始终白天 · English')
 expect(state.templates[0].config).toMatchObject({device_profile:'bx68',theme_mode:'light',language:'en',room_light:true})
 await page.getByRole('button',{name:'复制调整'}).click();await page.getByLabel('设备型号').selectOption('rk3568_r')
 await expect(page.getByText('高电平点亮 · 低电平熄灭')).toBeVisible()
 await page.getByRole('button',{name:'设备台账',exact:true}).click();await page.getByLabel('选择 ABC234').check();await page.locator('.v6-batch select').selectOption('1')
 page.on('dialog',d=>d.accept());await page.getByRole('button',{name:'批量下发'}).click();await expect.poll(()=>state.batches.length).toBe(1)
 expect(state.batches[0].config.device_profile).toBe('bx68');expect(state.batches[0].config.theme_mode).toBe('light')
 await page.getByRole('button',{name:'配置模板',exact:true}).click();await expect(page.getByLabel('设备型号')).toHaveValue('rk3568_r');await page.getByLabel('设备型号').selectOption('generic')
 await expect(page.getByLabel('同步侧边灯')).not.toBeChecked();await expect(page.getByLabel('同步侧边灯')).toBeDisabled()
 await page.getByLabel('设备型号').selectOption('bx68');await page.setViewportSize({width:1366,height:1000});await page.screenshot({path:'/tmp/roombeacon-model-templates.png',fullPage:true})
 await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
})
test('同型号仅提示；异型号批量下发可取消或确认，单台同样支持',async({page})=>{
 const state=await fixture(page);state.device.status='active';state.device.room_id='omm_test'
 state.templates.push({id:'1',revision:1,name:'BX template',config:{...config,device_profile:'bx68',theme_mode:'light',language:'en'}})
 Object.assign(state.device.metadata,{model:profiles[1].model,firmware:'custom'})
 await page.goto('/control');await page.getByLabel('选择 ABC234').check();await page.locator('.v6-batch select').selectOption('1')
 await expect(page.locator('.v6-batch')).toContainText('型号相同，可正常下发')
 await expect(page.locator('.v6-batch')).toContainText('模板灯控需升级 APK')
 const prompts:string[]=[];let accept=false
 page.on('dialog',async d=>{prompts.push(d.message());await (accept?d.accept():d.dismiss())})
 await page.getByRole('button',{name:'批量下发'}).click();await expect.poll(()=>state.batches.length).toBe(1)
 expect(prompts).toHaveLength(0);expect(state.batches[0].confirm_model_mismatch).toBe(false)
 Object.assign(state.device.metadata,{model:'special',config_schema:2})
 await page.getByRole('button',{name:'刷新状态'}).click()
 await expect(page.locator('.v6-batch')).toContainText('1 台型号不同')
 await expect(page.getByRole('button',{name:'批量下发'})).toBeEnabled()
 await page.getByRole('button',{name:'批量下发'}).click();expect(prompts).toHaveLength(1);expect(prompts[0]).toContain('special');expect(state.batches).toHaveLength(1)
 accept=true;await page.getByRole('button',{name:'批量下发'}).click();await expect.poll(()=>state.batches.length).toBe(2)
 expect(state.batches[1].confirm_model_mismatch).toBe(true)
 await page.getByRole('button',{name:'配置',exact:true}).click();await page.getByLabel('硬件安装模板',{exact:true}).selectOption('1')
 accept=false;await page.getByRole('button',{name:'保存并下发'}).click();expect(state.saved).toHaveLength(0)
 accept=true;await page.getByRole('button',{name:'保存并下发'}).click();await expect.poll(()=>state.saved.length).toBe(1)
 expect(state.saved[0].confirm_model_mismatch).toBe(true)
 expect(state.saved[0].config).toMatchObject({theme_mode:'light',language:'en',device_profile:'bx68'})
 expect(state.saved[0].config).not.toHaveProperty('confirm_model_mismatch')
})
test('回退到不同型号模板时确认后下发，取消保留当前配置',async({page})=>{
 const state=await fixture(page);state.device.status='active';state.device.room_id='omm_test';state.device.revision=3
 const rollbacks:any[]=[]
 await page.route('**/api/v6/admin/devices/'+sample.id+'/history',route=>route.fulfill({json:{data:[{revision:2,room_id:'omm_test',status:'active',config:{...config,device_profile:'bx68'}}]}}))
 await page.route('**/api/v6/admin/devices/'+sample.id+'/rollback',route=>{rollbacks.push(route.request().postDataJSON());return route.fulfill({json:{data:{}}})})
 await page.goto('/control');await page.getByRole('button',{name:'配置',exact:true}).click();await page.getByRole('button',{name:'配置历史'}).click()
 let accept=false;page.on('dialog',async d=>{expect(d.message()).toContain('确认强制下发');await (accept?d.accept():d.dismiss())})
 await page.getByRole('button',{name:'回退至此配置'}).click();expect(rollbacks).toHaveLength(0)
 accept=true;await page.getByRole('button',{name:'回退至此配置'}).click();await expect.poll(()=>rollbacks.length).toBe(1)
 expect(rollbacks[0]).toEqual({expected_revision:3,revision:2,confirm_model_mismatch:true})
})
