import {expect,type Page} from '@playwright/test'
import {hardwareDefaults,softwareDefaults,type CatalogTemplate,type Configuration} from '../src/api/configuration'
export const rooms=[
 {room_id:'omm_beijing',name:'同名会议室',region:'北京',region_id:'bj',location:'公司 / 中国 / 北京 / A座 / 2层 / 东区',location_nodes:[{id:'root',name:'公司'},{id:'cn',name:'中国'},{id:'bj',name:'北京'},{id:'bja',name:'A座'},{id:'bja2',name:'2层'},{id:'bja2e',name:'东区'}]},
 {room_id:'omm_shanghai',name:'同名会议室',region:'上海',region_id:'sh',location:'公司 / 中国 / 上海 / A座 / 2层',location_nodes:[{id:'root',name:'公司'},{id:'cn',name:'中国'},{id:'sh',name:'上海'},{id:'sha',name:'A座'},{id:'sha2',name:'2层'}]},
 {room_id:'omm_other',name:'其他会议室',region:'北京',region_id:'bj',location:'公司 / 中国 / 北京 / B座 / 3层',location_nodes:[{id:'root',name:'公司'},{id:'cn',name:'中国'},{id:'bj',name:'北京'},{id:'bjb',name:'B座'},{id:'bjb3',name:'3层'}]},
]
function template(id:string,kind:'hardware'|'software',name:string):CatalogTemplate{const spec=kind==='hardware'?hardwareDefaults():softwareDefaults();return {id,kind,name,spec,revision:2,published_version:1,archived:0,source:'manual',versions:[{template_id:id,version:1,name,spec:structuredClone(spec),actor:'test',created_at:1900000000}],tests:[],rooms:[],devices:[]}}
export async function fixture(page:Page,role='admin',logged=true){
 const state={logged,devices:rooms.map((r,i)=>({id:(i+1).toString().repeat(32),code:['ABC234','DEF567','GHJ890'][i],status:'active',room_id:r.room_id,revision:2,reported_revision:2,online:true,last_seen:1900000000,error:'',config:{version:'v6',portrait:false,room_light:false,node_id:'central',reload:0,theme_mode:'auto',language:'zh-CN',device_profile:'generic'},metadata:{model:'测试屏幕',serial:`TEST-${i}`,apk:'0.7.0',config_schema:3,android:'11',network:'ethernet',interfaces:[]}})),catalog:[template('hw','hardware','测试横屏硬件'),template('sw','software','测试中文软件')],configuration:{rooms:{},devices:{},deployments:[]} as Configuration,writes:[] as {path:string;body:any}[],conflict:false}
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname,method=route.request().method(),ok=(data:unknown)=>route.fulfill({json:{code:0,data}})
  if(path.endsWith('/auth/options'))return ok({feishu:true})
  if(path.endsWith('/auth/me'))return state.logged?(role==='pending'?route.fulfill({status:403,json:{code:403}}):ok({subject:'u',role,name:'测试管理员',csrf:'csrf'})):route.fulfill({status:401,json:{code:401}})
  if(path.endsWith('/auth/logout')){state.logged=false;return ok({})}
  if(path.endsWith('/auth/users'))return ok([{subject:'pending',name:'待授权用户',role:'pending'}])
  if(path==='/api/v6/admin/devices')return ok(state.devices)
  if(path==='/api/room-control/rooms')return ok(rooms)
  if(path==='/api/v6/admin/configuration')return ok(state.configuration)
  if(path==='/api/v6/admin/audit')return ok([{id:1,time:1900000000,actor:'opaque-user',action:'deployment',target:'opaque-device',detail:{actor_name:'测试管理员',target_name:'设备 ABC234',room_name:'测试会议室',hardware_name:'测试横屏硬件',hardware_version:1,software_name:'测试中文软件',software_version:2,before:{language:'zh-CN'},after:{language:'en'}}}])
  if(method==='GET'&&path==='/api/v6/admin/catalog')return ok(state.catalog)
  if(method==='GET'&&path==='/api/room-control/preview'){const now=Date.now();return ok({room:{room_id:'omm_beijing',name:'预览会议室',capacity:8,enabled:true},events:[],synced_at:new Date(now).toISOString(),valid_until:new Date(now+60000).toISOString(),server_time:new Date(now).toISOString(),titles_available:true,usage_owner:'official'})}
  if(path.startsWith('/api/room-control/usage/'))return ok({usage:{policy:{owner:'official',mode:'off',early_minutes:5,grace_minutes:10,release_delay_seconds:60,native_policy_cleared:false,release_verified:false,revision:'policy'},paused:true,record:null},audit:[],global_audit:[],writes_enabled:false})
  if(method!=='GET'){
   expect(route.request().headers()['x-rb-csrf']).toBe('csrf')
   const body=route.request().postDataJSON();state.writes.push({path,body})
   if(state.conflict)return route.fulfill({status:409,json:{code:409}})
   if(path==='/api/v6/admin/catalog'){const row=template(`template-${state.catalog.length}`,body.kind,body.name);Object.assign(row,{spec:body.spec,revision:1,published_version:0,versions:[]});state.catalog.push(row);return ok(row)}
   if(path.startsWith('/api/v6/admin/catalog/')){
    const id=path.split('/')[5],row=state.catalog.find(t=>t.id===id)!
    if(path.endsWith('/publish')){row.published_version++;row.versions.unshift({template_id:id,version:row.published_version,name:row.name,spec:structuredClone(row.spec),actor:'test',created_at:1900000000})}
    else if(path.endsWith('/archive'))row.archived=1
    else if(path.endsWith('/tests'))row.tests.push({id:'test',version:body.version,actor:'test',created_at:1900000000,value:{device_code:'ABC234',result:body.result,notes:body.notes}})
    else Object.assign(row,{name:body.name,spec:body.spec})
    row.revision++;return ok(row)
   }
   if(path==='/api/v6/admin/deployments/preview')return ok({room:{name:'同名会议室'},software:'测试中文软件',devices:[{code:'ABC234',hardware:'测试横屏硬件',before:{},after:{}}]})
   if(path==='/api/v6/admin/deployments'){
    const d=state.devices.find(d=>d.id===body.device_id)!;d.revision++;d.room_id=body.room_id;d.status='active'
    state.configuration.devices[d.id]={device_id:d.id,hardware_id:body.hardware_id,hardware_version:body.hardware_version,deployment_id:'deployment'}
    state.configuration.rooms[d.room_id]={room_id:d.room_id,software_id:body.software_id,software_version:body.software_version,revision:1,controller_id:d.id,rules:softwareDefaults().rules,policy_state:'applied',error:'',room_name:'同名会议室',location:'北京'}
    state.configuration.deployments.unshift({id:'deployment',device_id:d.id,room_id:d.room_id,hardware_id:body.hardware_id,hardware_version:body.hardware_version,software_id:body.software_id,software_version:body.software_version,device_revision:d.revision,reported_revision:d.reported_revision,state:'waiting',online:true,policy_state:'applied',error:'',created_at:1900000000,value:{device_code:d.code,room_name:'同名会议室',location:'北京',hardware_name:'测试横屏硬件',software_name:'测试中文软件',before:{},after:{}}})
    return ok({deployment_ids:['deployment']})
   }
   return ok({})
  }
  return route.fulfill({status:404,json:{code:404}})
 });return state
}
export async function selectDeployment(page:Page){await page.getByRole('button',{name:'配置与部署',exact:true}).first().click();const panel=page.getByRole('dialog');await panel.getByLabel('硬件安装模板',{exact:true}).selectOption('hw');await panel.getByLabel('软件模板',{exact:true}).selectOption('sw');return panel}
