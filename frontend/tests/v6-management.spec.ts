import {test,expect,type Page} from '@playwright/test'
const config={version:'v6',portrait:false,room_light:true,node_id:'central',reload:0}
const sample={id:'a'.repeat(32),code:'ABC234',status:'pending',room_id:'',revision:1,reported_revision:1,online:true,last_seen:1900000000,error:'',config,
  metadata:{model:'测试样机 BX68',serial:'TEST-SN-001',apk:'0.6.0',android:'11',network:'ethernet',light_supported:true,interfaces:[{name:'eth0',mac:'02:00:00:00:00:01',addresses:['192.0.2.10']}]}}
async function fixture(page:Page,role='admin',logged=true){
 const state={logged,device:structuredClone(sample),saved:[] as any[]}
 await page.route('**/api/**',async route=>{
  const p=new URL(route.request().url()).pathname,method=route.request().method(),ok=(data:unknown)=>route.fulfill({json:{code:0,data}})
  if(p==='/api/v6/auth/options')return ok({feishu:true})
  if(p==='/api/v6/auth/session'){state.logged=true;return ok({authenticated:true})}
  if(p==='/api/v6/auth/me')return state.logged?ok({subject:'u',name:'测试管理员',role,csrf:'test-csrf'}):route.fulfill({status:401,json:{code:401}})
  if(p==='/api/v6/auth/logout'){state.logged=false;return ok({})}
  if(p==='/api/v6/admin/devices')return ok([state.device])
  if(p==='/api/room-control/rooms')return ok([{room_id:'omm_test',name:'测试会议室',region:'北京',location:'2F'}])
  if(p==='/api/v6/admin/templates'||p==='/api/v6/admin/audit')return ok([])
  if(p==='/api/v6/auth/users')return ok([{subject:'pending-user',name:'待授权用户',role:'pending'}])
  if(p==='/api/v6/admin/devices/'+sample.id&&method==='PUT'){
   expect(route.request().headers()['x-rb-csrf']).toBe('test-csrf')
   const body=route.request().postDataJSON();state.saved.push(body);state.device={...state.device,...body,revision:2,reported_revision:1};return ok(state.device)
  }
  return route.fulfill({status:404,json:{code:404}})
 });return state
}
test('V6 登录、短码核对与后台激活下发',async({page})=>{
 const state=await fixture(page,'admin',false);await page.goto('/control')
 await expect(page.getByRole('link',{name:'飞书扫码 / 快捷登录'})).toHaveAttribute('href','/api/v6/auth/feishu/start')
 await page.getByLabel('主控凭证').fill('test-secret');await page.getByRole('button',{name:'进入管理后台'}).click()
 await expect(page.getByText('ABC 234',{exact:true})).toBeVisible();await expect(page.getByText('有线 / PoE')).toBeVisible()
 await page.getByRole('button',{name:'配置',exact:true}).click()
 await page.getByRole('dialog').getByLabel('设备状态').selectOption('active');await page.getByLabel('分配会议室').selectOption('omm_test')
 await page.getByRole('button',{name:'保存并下发'}).click();await expect(page.getByText('待设备应用',{exact:true})).toBeVisible()
 expect(state.saved[0].expected_revision).toBe(1);expect(state.saved[0].room_id).toBe('omm_test')
 await expect(page.getByRole('dialog')).toHaveCount(0);await page.setViewportSize({width:1440,height:1000})
 await page.screenshot({path:'/tmp/roombeacon-v6-admin-test.png',fullPage:true})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
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
